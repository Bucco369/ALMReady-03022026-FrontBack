"""Calculation routes: EVE/NII, What-If, results, chart-data, calc-progress."""

from __future__ import annotations

import json
from concurrent.futures import as_completed
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException

import app.state as state
from app.config import (
    _CATEGORY_SIDE_MAP,
    _FREQ_TO_MONTHS,
    _PRODUCT_TEMPLATE_TO_MOTOR,
    _REF_INDEX_TO_MOTOR,
)
from app.schemas import (
    CalculateRequest,
    CalculationResultsResponse,
    ChartDataResponse,
    ScenarioResultItem,
    WhatIfBucketDelta,
    WhatIfCalculateRequest,
    WhatIfModificationItem,
    WhatIfMonthDelta,
    WhatIfResultsResponse,
)
from app.session import (
    _assert_session_exists,
    _calc_params_path,
    _chart_data_path,
    _motor_positions_path,
    _positions_path,
    _results_path,
)
from app.parsers.balance_parser import _reconstruct_motor_dataframe
from app.parsers.curves_parser import _build_forward_curve_set

router = APIRouter()


# ── Calc progress ───────────────────────────────────────────────────────────

@router.get("/api/sessions/{session_id}/calc-progress")
def get_calc_progress(session_id: str):
    progress = state._calc_progress.get(session_id)
    if progress is None:
        return {"phase": "idle", "completed": 0, "total": 0, "pct": 0, "phase_label": ""}

    phase = progress.get("phase", "preparing")
    completed = progress.get("completed", 0)
    total = progress.get("total", 1)
    current_task = progress.get("current_task", "")

    if phase == "preparing":
        pct = 3
    elif total > 0:
        pct = 5 + round((completed / total) * 90)
    else:
        pct = 5

    return {
        "phase": phase,
        "completed": completed,
        "total": total,
        "pct": min(pct, 95),
        "phase_label": current_task,
    }


# ── Core calculation ────────────────────────────────────────────────────────

@router.post("/api/sessions/{session_id}/calculate", response_model=CalculationResultsResponse)
def calculate_eve_nii(session_id: str, req: CalculateRequest) -> CalculationResultsResponse:
    from engine.services.regulatory_curves import build_regulatory_curve_sets

    _assert_session_exists(session_id)

    state._calc_progress[session_id] = {
        "completed": 0, "total": 0,
        "phase": "preparing", "current_task": "Loading positions…",
    }

    # 1. Determine analysis date
    if req.analysis_date:
        try:
            analysis_date = date.fromisoformat(req.analysis_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid analysis_date: {req.analysis_date}")
    else:
        analysis_date = date.today()

    risk_free_index = req.risk_free_index or req.discount_curve_id

    # 2. Load motor positions
    state._calc_progress[session_id]["current_task"] = "Loading positions…"
    motor_df = _reconstruct_motor_dataframe(session_id)

    # 3. Build base ForwardCurveSet
    try:
        base_curve_set = _build_forward_curve_set(session_id, analysis_date)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error building curve set: {exc}")

    if req.discount_curve_id not in base_curve_set.curves:
        available = base_curve_set.available_indices
        raise HTTPException(
            status_code=400,
            detail=(
                f"Discount curve '{req.discount_curve_id}' not found. "
                f"Available: {available}"
            ),
        )

    # 4. Build regulatory scenario curve sets
    state._calc_progress[session_id]["current_task"] = "Building scenario curves…"
    try:
        scenario_curve_sets = build_regulatory_curve_sets(
            base_set=base_curve_set,
            scenarios=req.scenarios,
            risk_free_index=risk_free_index,
            currency=req.currency,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Error building scenario curves: {exc}",
        )

    # 5+6. Run EVE and NII scenarios in parallel
    try:
        from engine.services.nii import compute_nii_margin_set
        effective_margin_set = compute_nii_margin_set(
            motor_df,
            curve_set=base_curve_set,
            risk_free_index=risk_free_index,
            as_of=base_curve_set.analysis_date,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Margin calibration error: {exc}")

    if state._executor is None:
        raise HTTPException(status_code=503, detail="Process pool not ready. Server may still be starting.")

    import engine.workers as _workers
    from engine.config import NII_HORIZON_MONTHS

    _unified_tag: dict = {}

    _unified_tag[state._executor.submit(
        _workers.eve_nii_unified,
        motor_df, base_curve_set, base_curve_set,
        req.discount_curve_id, effective_margin_set,
        risk_free_index, True, NII_HORIZON_MONTHS,
    )] = None
    for sc_name, sc_set in scenario_curve_sets.items():
        _unified_tag[state._executor.submit(
            _workers.eve_nii_unified,
            motor_df, sc_set, sc_set,
            req.discount_curve_id, effective_margin_set,
            risk_free_index, True, NII_HORIZON_MONTHS,
        )] = sc_name

    total_tasks = len(_unified_tag)
    state._calc_progress[session_id].update({
        "phase": "computing", "completed": 0, "total": total_tasks,
        "current_task": "Starting scenarios…",
    })

    base_eve: float = 0.0
    scenario_eve: dict[str, float] = {}
    base_nii: float = 0.0
    scenario_nii: dict[str, float] = {}
    errors: list[str] = []
    completed_count = 0

    _chart_eve_buckets: list[dict] = []
    _chart_nii_monthly: list[dict] = []

    for fut in as_completed(_unified_tag):
        sc = _unified_tag[fut]
        label = sc if sc is not None else "base"
        completed_count += 1

        if session_id in state._calc_progress:
            state._calc_progress[session_id].update({
                "completed": completed_count,
                "current_task": f"EVE+NII: {label}",
            })

        try:
            result: dict = fut.result()
            eve_val = float(result["eve_scalar"])
            nii_val = float(result["nii_scalar"])
            if sc is None:
                base_eve = eve_val
                base_nii = nii_val
            else:
                scenario_eve[sc] = eve_val
                scenario_nii[sc] = nii_val

            eve_bucket_list = result.get("eve_buckets")
            if eve_bucket_list:
                by_bucket: dict[str, dict] = {}
                for b in eve_bucket_list:
                    bname = b["bucket_name"]
                    if bname not in by_bucket:
                        by_bucket[bname] = {
                            "scenario": label,
                            "bucket_name": bname,
                            "bucket_start_years": b["bucket_start_years"],
                            "bucket_end_years": b["bucket_end_years"],
                            "asset_pv": 0.0, "liability_pv": 0.0, "net_pv": 0.0,
                        }
                    sg = b["side_group"]
                    if sg == "asset":
                        by_bucket[bname]["asset_pv"] = float(b["pv_total"])
                    elif sg == "liability":
                        by_bucket[bname]["liability_pv"] = float(b["pv_total"])
                    elif sg == "net":
                        by_bucket[bname]["net_pv"] = float(b["pv_total"])
                _chart_eve_buckets.extend(by_bucket.values())

            nii_monthly_list = result.get("nii_monthly")
            if nii_monthly_list:
                for m in nii_monthly_list:
                    _chart_nii_monthly.append({
                        "scenario": label,
                        "month_index": m["month_index"],
                        "month_label": m["month_label"],
                        "interest_income": m["interest_income"],
                        "interest_expense": m["interest_expense"],
                        "net_nii": m["net_nii"],
                    })

        except Exception as exc:
            errors.append(f"EVE+NII[{label}]: {type(exc).__name__}: {exc}")

    state._calc_progress.pop(session_id, None)

    if errors:
        raise HTTPException(
            status_code=500,
            detail="Worker errors (all scenarios attempted):\n" + "\n".join(errors),
        )

    # 7. Map to frontend contract
    scenario_items: list[ScenarioResultItem] = []

    for scenario_name in req.scenarios:
        sc_eve = scenario_eve.get(scenario_name, base_eve)
        sc_nii = scenario_nii.get(scenario_name, base_nii)
        delta_eve = sc_eve - base_eve
        delta_nii = sc_nii - base_nii

        scenario_items.append(ScenarioResultItem(
            scenario_id=scenario_name,
            scenario_name=scenario_name,
            eve=sc_eve,
            nii=sc_nii,
            delta_eve=delta_eve,
            delta_nii=delta_nii,
        ))

    if scenario_items:
        worst_item = min(scenario_items, key=lambda s: s.delta_eve)
        worst_eve = worst_item.eve
        worst_delta_eve = worst_item.delta_eve
        worst_scenario_name = worst_item.scenario_name
    else:
        worst_eve = base_eve
        worst_delta_eve = 0.0
        worst_scenario_name = "base"

    calculated_at = datetime.now(timezone.utc).isoformat()

    response = CalculationResultsResponse(
        session_id=session_id,
        base_eve=base_eve,
        base_nii=base_nii,
        worst_case_eve=worst_eve,
        worst_case_delta_eve=worst_delta_eve,
        worst_case_scenario=worst_scenario_name,
        scenario_results=scenario_items,
        calculated_at=calculated_at,
    )

    _chart_data_path(session_id).write_text(
        json.dumps({
            "session_id": session_id,
            "eve_buckets": _chart_eve_buckets,
            "nii_monthly": _chart_nii_monthly,
        }, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    _results_path(session_id).write_text(
        response.model_dump_json(indent=2),
        encoding="utf-8",
    )

    calc_params = {
        "discount_curve_id": req.discount_curve_id,
        "scenarios": req.scenarios,
        "analysis_date": analysis_date.isoformat(),
        "currency": req.currency,
        "risk_free_index": risk_free_index,
        "worst_case_scenario": worst_scenario_name,
        "nii_horizon_months": NII_HORIZON_MONTHS,
    }
    _calc_params_path(session_id).write_text(
        json.dumps(calc_params, indent=2),
        encoding="utf-8",
    )

    return response


# ── Results retrieval ───────────────────────────────────────────────────────

@router.get("/api/sessions/{session_id}/results", response_model=CalculationResultsResponse)
def get_calculation_results(session_id: str) -> CalculationResultsResponse:
    _assert_session_exists(session_id)
    results_file = _results_path(session_id)
    if not results_file.exists():
        raise HTTPException(status_code=404, detail="No calculation results yet. Run /calculate first.")
    payload = json.loads(results_file.read_text(encoding="utf-8"))
    return CalculationResultsResponse(**payload)


@router.get("/api/sessions/{session_id}/results/chart-data", response_model=ChartDataResponse)
def get_chart_data(session_id: str) -> ChartDataResponse:
    _assert_session_exists(session_id)

    cache_path = _chart_data_path(session_id)
    if not cache_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No chart data available. Run /calculate first.",
        )
    return ChartDataResponse.model_validate_json(cache_path.read_text(encoding="utf-8"))


# ── What-If helpers ─────────────────────────────────────────────────────────

def _create_synthetic_motor_row(
    mod: WhatIfModificationItem,
    analysis_date: date,
) -> dict[str, Any]:
    mapping = _PRODUCT_TEMPLATE_TO_MOTOR.get(mod.productTemplateId or "", {})
    sct = mapping.get("source_contract_type", "fixed_bullet")
    side = mapping.get("side", _CATEGORY_SIDE_MAP.get(mod.category or "asset", "A"))

    if mod.startDate:
        try:
            start = date.fromisoformat(mod.startDate)
        except ValueError:
            start = analysis_date
    else:
        start = analysis_date

    if mod.maturityDate:
        try:
            mat = date.fromisoformat(mod.maturityDate)
        except ValueError:
            mat = None
    else:
        mat = None

    if mat is None and mod.maturity and mod.maturity > 0:
        from datetime import timedelta
        mat = start + timedelta(days=round(mod.maturity * 365.25))

    if mat is None:
        from datetime import timedelta
        mat = start + timedelta(days=365)

    fixed_rate = mod.rate if mod.rate is not None else 0.0
    spread_val = (mod.spread or 0.0) / 10000.0 if mod.spread else 0.0

    is_variable = "variable" in sct
    raw_ref = (mod.refIndex or "").strip()
    ref_index = _REF_INDEX_TO_MOTOR.get(raw_ref, raw_ref) or "EUR_ESTR_OIS"

    freq_str = (mod.paymentFreq or "annual").lower()
    coupon_months = _FREQ_TO_MONTHS.get(freq_str, 12)

    reprice_str = (mod.repricingFreq or freq_str).lower()
    reprice_months = _FREQ_TO_MONTHS.get(reprice_str, coupon_months)

    payment_freq_str = f"{coupon_months}M"
    repricing_freq_str = f"{reprice_months}M" if is_variable else None

    row: dict[str, Any] = {
        "contract_id": f"whatif_{mod.id}",
        "side": side,
        "source_contract_type": sct,
        "notional": abs(mod.notional or 0.0),
        "fixed_rate": 0.0 if is_variable else fixed_rate,
        "spread": spread_val if is_variable else 0.0,
        "start_date": start,
        "maturity_date": mat,
        "index_name": ref_index if is_variable else None,
        "next_reprice_date": start if is_variable else None,
        "daycount_base": "ACT/360",
        "payment_freq": payment_freq_str,
        "repricing_freq": repricing_freq_str,
        "currency": mod.currency or "EUR",
        "floor_rate": None,
        "cap_rate": None,
    }
    return row


def _build_whatif_delta_dataframe(
    modifications: list[WhatIfModificationItem],
    motor_df: pd.DataFrame,
    balance_rows: list[dict[str, Any]],
    analysis_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    add_rows: list[dict[str, Any]] = []
    remove_ids: list[str] = []

    for mod in modifications:
        if mod.type == "add":
            add_rows.append(_create_synthetic_motor_row(mod, analysis_date))

        elif mod.type == "remove":
            if mod.removeMode == "contracts" and mod.contractIds:
                remove_ids.extend(mod.contractIds)
            elif mod.removeMode == "all" and mod.subcategory:
                for row in balance_rows:
                    sub_id = row.get("subcategory_id", "")
                    if sub_id == mod.subcategory:
                        cid = row.get("contract_id")
                        if cid:
                            remove_ids.append(cid)

    add_df = pd.DataFrame(add_rows) if add_rows else pd.DataFrame()
    if add_df.empty and motor_df is not None and not motor_df.empty:
        add_df = motor_df.iloc[0:0].copy()

    if remove_ids and motor_df is not None and not motor_df.empty and "contract_id" in motor_df.columns:
        unique_ids = set(remove_ids)
        remove_df = motor_df[motor_df["contract_id"].isin(unique_ids)].copy()
    else:
        remove_df = motor_df.iloc[0:0].copy() if (motor_df is not None and not motor_df.empty) else pd.DataFrame()

    date_cols = ["start_date", "maturity_date", "next_reprice_date"]
    for col in date_cols:
        if col in add_df.columns:
            add_df[col] = add_df[col].apply(
                lambda d: d if isinstance(d, date) else None
            )

    numeric_cols = ["notional", "fixed_rate", "spread", "floor_rate", "cap_rate"]
    for col in numeric_cols:
        if col in add_df.columns:
            add_df[col] = pd.to_numeric(add_df[col], errors="coerce")

    return add_df, remove_df


# ── What-If calculation ─────────────────────────────────────────────────────

@router.post("/api/sessions/{session_id}/calculate/whatif", response_model=WhatIfResultsResponse)
def calculate_whatif(session_id: str, req: WhatIfCalculateRequest) -> WhatIfResultsResponse:
    from engine.services.regulatory_curves import build_regulatory_curve_sets
    from engine.services.eve import build_eve_cashflows
    from engine.services.eve_analytics import compute_eve_full
    from engine.services.nii import compute_nii_from_cashflows, compute_nii_margin_set
    from engine.config import NII_HORIZON_MONTHS

    _assert_session_exists(session_id)

    # 1. Load stored calculation params
    params_file = _calc_params_path(session_id)
    if not params_file.exists():
        raise HTTPException(
            status_code=404,
            detail="No base calculation found. Run /calculate first.",
        )
    calc_params = json.loads(params_file.read_text(encoding="utf-8"))

    try:
        analysis_date = date.fromisoformat(calc_params["analysis_date"])
    except (KeyError, ValueError):
        analysis_date = date.today()

    discount_curve_id = calc_params.get("discount_curve_id", "EUR_ESTR_OIS")
    scenarios = calc_params.get("scenarios", [])
    risk_free_index = calc_params.get("risk_free_index", discount_curve_id)
    worst_scenario = calc_params.get("worst_case_scenario", "base")

    # 2. Load motor positions (for removes)
    motor_path = _motor_positions_path(session_id)
    if motor_path.exists():
        motor_df = _reconstruct_motor_dataframe(session_id)
    else:
        motor_df = pd.DataFrame()

    pos_path = _positions_path(session_id)
    balance_rows: list[dict[str, Any]] = []
    if pos_path.exists():
        balance_rows = json.loads(pos_path.read_text(encoding="utf-8"))

    # 3. Build delta DataFrames
    add_df, remove_df = _build_whatif_delta_dataframe(
        req.modifications, motor_df, balance_rows, analysis_date,
    )

    has_adds = not add_df.empty
    has_removes = not remove_df.empty

    if not has_adds and not has_removes:
        return WhatIfResultsResponse(
            session_id=session_id,
            base_eve_delta=0.0,
            worst_eve_delta=0.0,
            base_nii_delta=0.0,
            worst_nii_delta=0.0,
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

    # 4. Build curve sets
    try:
        base_curve_set = _build_forward_curve_set(session_id, analysis_date)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error building curve set: {exc}")

    try:
        scenario_curve_sets = build_regulatory_curve_sets(
            base_set=base_curve_set,
            scenarios=scenarios,
            risk_free_index=risk_free_index,
            currency=calc_params.get("currency", "EUR"),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error building scenario curves: {exc}")

    # 5+6. Unified EVE+NII deltas
    def _unified_whatif_map(df: pd.DataFrame):
        eve_data: dict[tuple[str, str], dict[str, float]] = {}
        eve_meta: dict[str, float] = {}
        nii_data: dict[tuple[str, int], dict[str, float]] = {}
        if df.empty:
            return eve_data, eve_meta, nii_data

        try:
            margin_set = compute_nii_margin_set(
                df,
                curve_set=base_curve_set,
                risk_free_index=risk_free_index,
                as_of=base_curve_set.analysis_date,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"What-If margin calibration error: {exc}")

        scenario_items: list[tuple[str, Any, Any]] = [
            ("base", base_curve_set, base_curve_set),
        ]
        for sc_name, sc_set in scenario_curve_sets.items():
            scenario_items.append((sc_name, sc_set, sc_set))

        for sc_label, disc_set, proj_set in scenario_items:
            try:
                cashflows = build_eve_cashflows(
                    df,
                    analysis_date=disc_set.analysis_date,
                    projection_curve_set=proj_set,
                )

                _, eve_buckets = compute_eve_full(
                    cashflows,
                    discount_curve_set=disc_set,
                    discount_index=discount_curve_id,
                    include_buckets=True,
                )
                if eve_buckets:
                    for b in eve_buckets:
                        bname = b["bucket_name"]
                        sg = b["side_group"]
                        if sg in ("asset", "liability"):
                            key = (sc_label, bname)
                            if key not in eve_data:
                                eve_data[key] = {"asset": 0.0, "liab": 0.0}
                            if sg == "asset":
                                eve_data[key]["asset"] = float(b["pv_total"])
                            else:
                                eve_data[key]["liab"] = float(b["pv_total"])
                            if bname not in eve_meta:
                                eve_meta[bname] = float(b["bucket_start_years"])

                nii_result = compute_nii_from_cashflows(
                    cashflows, df, proj_set,
                    analysis_date=disc_set.analysis_date,
                    horizon_months=NII_HORIZON_MONTHS,
                    balance_constant=True,
                    margin_set=margin_set,
                    risk_free_index=risk_free_index,
                )
                for m in nii_result.monthly_breakdown:
                    mi = m["month_index"]
                    nii_data[(sc_label, mi)] = {
                        "income": m["interest_income"],
                        "expense": m["interest_expense"],
                        "label": m["month_label"],
                    }

            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"What-If unified [{sc_label}] error: {exc}",
                )

        return eve_data, eve_meta, nii_data

    add_eve, add_meta, add_nii = _unified_whatif_map(add_df) if has_adds else ({}, {}, {})
    rem_eve, rem_meta, rem_nii = _unified_whatif_map(remove_df) if has_removes else ({}, {}, {})

    # EVE: Build per-bucket delta list
    bucket_meta = {**rem_meta, **add_meta}
    all_sb_keys = set(add_eve) | set(rem_eve)
    eve_bucket_deltas: list[WhatIfBucketDelta] = []

    for sc, bname in sorted(all_sb_keys, key=lambda x: (x[0], bucket_meta.get(x[1], 0.0))):
        add_vals = add_eve.get((sc, bname), {"asset": 0.0, "liab": 0.0})
        rem_vals = rem_eve.get((sc, bname), {"asset": 0.0, "liab": 0.0})
        eve_bucket_deltas.append(WhatIfBucketDelta(
            scenario=sc,
            bucket_name=bname,
            bucket_start_years=bucket_meta.get(bname, 0.0),
            asset_pv_delta=add_vals["asset"] - rem_vals["asset"],
            liability_pv_delta=add_vals["liab"] - rem_vals["liab"],
        ))

    eve_by_scenario: dict[str, float] = {}
    for d in eve_bucket_deltas:
        eve_by_scenario[d.scenario] = (
            eve_by_scenario.get(d.scenario, 0.0) + d.asset_pv_delta + d.liability_pv_delta
        )

    base_eve_delta = eve_by_scenario.pop("base", 0.0)
    scenario_eve_deltas = eve_by_scenario
    worst_eve_delta = scenario_eve_deltas.get(worst_scenario, base_eve_delta)

    # NII: Build per-month delta list
    all_sm_keys = set(add_nii) | set(rem_nii)
    nii_month_deltas: list[WhatIfMonthDelta] = []

    for sc, mi in sorted(all_sm_keys, key=lambda x: (x[0], x[1])):
        add_vals = add_nii.get((sc, mi), {"income": 0.0, "expense": 0.0, "label": ""})
        rem_vals = rem_nii.get((sc, mi), {"income": 0.0, "expense": 0.0, "label": ""})
        label = add_vals.get("label") or rem_vals.get("label") or f"M{mi}"
        nii_month_deltas.append(WhatIfMonthDelta(
            scenario=sc,
            month_index=mi,
            month_label=str(label),
            income_delta=add_vals["income"] - rem_vals["income"],
            expense_delta=add_vals["expense"] - rem_vals["expense"],
        ))

    nii_by_scenario: dict[str, float] = {}
    for d in nii_month_deltas:
        nii_by_scenario[d.scenario] = (
            nii_by_scenario.get(d.scenario, 0.0) + d.income_delta + d.expense_delta
        )

    base_nii_delta = nii_by_scenario.pop("base", 0.0)
    scenario_nii_deltas = nii_by_scenario
    worst_nii_delta = scenario_nii_deltas.get(worst_scenario, base_nii_delta)

    return WhatIfResultsResponse(
        session_id=session_id,
        base_eve_delta=base_eve_delta,
        worst_eve_delta=worst_eve_delta,
        base_nii_delta=base_nii_delta,
        worst_nii_delta=worst_nii_delta,
        scenario_eve_deltas=scenario_eve_deltas,
        scenario_nii_deltas=scenario_nii_deltas,
        eve_bucket_deltas=eve_bucket_deltas,
        nii_month_deltas=nii_month_deltas,
        calculated_at=datetime.now(timezone.utc).isoformat(),
    )
