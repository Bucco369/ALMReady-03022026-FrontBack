"""What-If V2 routes: decompose preview + generalized EVE/NII calculation.

This router replaces the 1:1 synthetic-row approach in calculate.py with
the N-position decomposer, supporting grace periods, mixed rates, and
multiple amortization types.

The existing /api/sessions/{sid}/calculate/whatif endpoint in calculate.py
remains for backward compatibility.  The new endpoints live under
/api/sessions/{sid}/whatif/.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException

import app.state as state
from app.schemas import (
    DecomposeResponse,
    DecomposedPosition,
    FindLimitRequest,
    FindLimitResponse,
    LoanSpecItem,
    WhatIfBucketDelta,
    WhatIfModificationItem,
    WhatIfMonthDelta,
    WhatIfResultsResponse,
    WhatIfV2CalculateRequest,
)
from app.session import (
    _assert_session_exists,
    _calc_params_path,
    _motor_positions_path,
)
from app.parsers.balance_parser import _reconstruct_motor_dataframe
from app.parsers.curves_parser import _build_forward_curve_set

from engine.services.whatif.decomposer import LoanSpec, decompose_loan

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

def _loan_spec_from_item(item: LoanSpecItem, analysis_date: date) -> LoanSpec:
    """Convert a Pydantic LoanSpecItem into the decomposer's LoanSpec."""
    start = None
    if item.start_date:
        try:
            start = date.fromisoformat(item.start_date)
        except ValueError:
            start = None

    return LoanSpec(
        notional=abs(item.notional),
        term_years=item.term_years,
        side=item.side,
        currency=item.currency or "EUR",
        rate_type=item.rate_type,
        fixed_rate=item.fixed_rate,
        variable_index=item.variable_index,
        spread_bps=item.spread_bps,
        mixed_fixed_years=item.mixed_fixed_years,
        amortization=item.amortization,
        grace_years=item.grace_years,
        daycount=item.daycount,
        payment_freq=item.payment_freq,
        repricing_freq=item.repricing_freq,
        start_date=start,
        analysis_date=analysis_date,
        floor_rate=item.floor_rate,
        cap_rate=item.cap_rate,
        id_prefix=f"whatif_{item.id}",
    )


def _decompose_additions(
    additions: list[LoanSpecItem],
    analysis_date: date,
) -> pd.DataFrame:
    """Decompose all LoanSpecItems into a single motor-positions DataFrame."""
    all_rows: list[dict[str, Any]] = []
    for item in additions:
        spec = _loan_spec_from_item(item, analysis_date)
        df = decompose_loan(spec)
        all_rows.extend(df.to_dict("records"))
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def _build_remove_df(
    removals: list[WhatIfModificationItem],
    motor_df: pd.DataFrame,
    balance_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    """Build the removal DataFrame from the existing motor positions."""
    remove_ids: list[str] = []
    for mod in removals:
        if mod.removeMode == "contracts" and mod.contractIds:
            remove_ids.extend(mod.contractIds)
        elif mod.removeMode == "all" and mod.subcategory:
            for row in balance_rows:
                if row.get("subcategory_id", "") == mod.subcategory:
                    cid = row.get("contract_id")
                    if cid:
                        remove_ids.append(cid)

    if remove_ids and motor_df is not None and not motor_df.empty and "contract_id" in motor_df.columns:
        return motor_df[motor_df["contract_id"].isin(set(remove_ids))].copy()

    return motor_df.iloc[0:0].copy() if (motor_df is not None and not motor_df.empty) else pd.DataFrame()


def _positions_to_response(df: pd.DataFrame) -> list[DecomposedPosition]:
    """Convert a decomposed DataFrame to a list of response models."""
    positions: list[DecomposedPosition] = []
    for _, row in df.iterrows():
        positions.append(DecomposedPosition(
            contract_id=row["contract_id"],
            side=row["side"],
            source_contract_type=row["source_contract_type"],
            notional=float(row["notional"]),
            fixed_rate=float(row["fixed_rate"]),
            spread=float(row["spread"]),
            start_date=str(row["start_date"]),
            maturity_date=str(row["maturity_date"]),
            index_name=row.get("index_name"),
            next_reprice_date=str(row["next_reprice_date"]) if row.get("next_reprice_date") else None,
            daycount_base=row["daycount_base"],
            payment_freq=row["payment_freq"],
            repricing_freq=row.get("repricing_freq"),
            currency=row["currency"],
            floor_rate=row.get("floor_rate"),
            cap_rate=row.get("cap_rate"),
            rate_type=row.get("rate_type", "fixed"),
        ))
    return positions


# ── Decompose preview ─────────────────────────────────────────────────────

@router.post(
    "/api/sessions/{session_id}/whatif/decompose",
    response_model=DecomposeResponse,
)
def decompose_preview(session_id: str, item: LoanSpecItem) -> DecomposeResponse:
    """Preview the motor positions that a LoanSpec would generate.

    This is a dry-run: no EVE/NII calculation, just the decomposition.
    Useful for the frontend to show position details before calculating.
    """
    _assert_session_exists(session_id)

    # Resolve analysis_date from stored calc params (or today)
    params_file = _calc_params_path(session_id)
    if params_file.exists():
        calc_params = json.loads(params_file.read_text(encoding="utf-8"))
        try:
            analysis_date = date.fromisoformat(calc_params["analysis_date"])
        except (KeyError, ValueError):
            analysis_date = date.today()
    else:
        analysis_date = date.today()

    spec = _loan_spec_from_item(item, analysis_date)

    try:
        df = decompose_loan(spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    positions = _positions_to_response(df)
    return DecomposeResponse(
        session_id=session_id,
        positions=positions,
        position_count=len(positions),
    )


# ── Full What-If calculation ──────────────────────────────────────────────

@router.post(
    "/api/sessions/{session_id}/whatif/calculate",
    response_model=WhatIfResultsResponse,
)
def calculate_whatif_v2(
    session_id: str,
    req: WhatIfV2CalculateRequest,
) -> WhatIfResultsResponse:
    """Generalized What-If: decompose additions + remove positions → EVE/NII delta.

    This replaces the 1:1 synthetic-row approach with N-position decomposition
    supporting grace periods, mixed rates, and multiple amortization types.
    """
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

    # 2. Decompose additions into motor positions
    try:
        add_df = _decompose_additions(req.additions, analysis_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Decomposition error: {exc}")

    # 3. Build removal DataFrame
    motor_path = _motor_positions_path(session_id)
    motor_json_path = motor_path.with_suffix(".json")
    if motor_path.exists() or motor_json_path.exists():
        motor_df = _reconstruct_motor_dataframe(session_id)
    else:
        motor_df = pd.DataFrame()

    from app.parsers.balance_parser import _read_positions_file
    balance_rows: list[dict[str, Any]] = _read_positions_file(session_id) or []

    remove_df = _build_remove_df(req.removals, motor_df, balance_rows)

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

    # 5. Unified EVE+NII calculation (reuses same pipeline as calculate.py)
    def _compute_eve_nii(df: pd.DataFrame):
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
                    detail=f"What-If [{sc_label}] computation error: {exc}",
                )

        return eve_data, eve_meta, nii_data

    add_eve, add_meta, add_nii = _compute_eve_nii(add_df) if has_adds else ({}, {}, {})
    rem_eve, rem_meta, rem_nii = _compute_eve_nii(remove_df) if has_removes else ({}, {}, {})

    # 6. Assemble EVE bucket deltas
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

    # 7. Assemble NII month deltas
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


# ── Find Limit ────────────────────────────────────────────────────────────


def _resolve_base_metric(
    results: dict[str, Any],
    target_metric: str,
    target_scenario: str,
) -> float:
    """Extract the current portfolio metric from stored calculation results."""
    if target_scenario == "base":
        return float(results.get(f"base_{target_metric}", 0.0))

    # For "worst" or a specific scenario, look in scenario_results
    if target_scenario == "worst":
        return float(results.get(f"worst_case_{target_metric}", 0.0))

    # Specific scenario: look in scenario_results array
    for sr in results.get("scenario_results", []):
        if sr.get("scenario_name") == target_scenario:
            if target_metric == "eve":
                return float(sr.get("eve", 0.0))
            else:
                return float(sr.get("nii", 0.0))

    # Fallback: use base
    return float(results.get(f"base_{target_metric}", 0.0))


def _compute_eve_nii_scalar(
    df: pd.DataFrame,
    disc_set: Any,
    proj_set: Any,
    discount_curve_id: str,
    risk_free_index: str,
    margin_set: Any,
    horizon_months: int,
) -> tuple[float, float]:
    """Compute scalar EVE and NII for a DataFrame of positions.

    Returns (eve_scalar, nii_scalar).
    """
    from engine.services.eve import build_eve_cashflows
    from engine.services.eve_analytics import compute_eve_full
    from engine.services.nii import compute_nii_from_cashflows

    if df.empty:
        return 0.0, 0.0

    cashflows = build_eve_cashflows(
        df,
        analysis_date=disc_set.analysis_date,
        projection_curve_set=proj_set,
    )

    eve_scalar, _ = compute_eve_full(
        cashflows,
        discount_curve_set=disc_set,
        discount_index=discount_curve_id,
        include_buckets=False,
    )

    nii_result = compute_nii_from_cashflows(
        cashflows, df, proj_set,
        analysis_date=disc_set.analysis_date,
        horizon_months=horizon_months,
        balance_constant=True,
        margin_set=margin_set,
        risk_free_index=risk_free_index,
    )

    return float(eve_scalar), float(nii_result.aggregate_nii)


@router.post(
    "/api/sessions/{session_id}/whatif/find-limit",
    response_model=FindLimitResponse,
)
def find_limit(session_id: str, req: FindLimitRequest) -> FindLimitResponse:
    """Solve for a single product variable to reach a metric limit.

    Uses linear scaling for notional (O(1)) or binary search for
    rate/maturity/spread (O(~15 iterations)).
    """
    import time
    from engine.services.regulatory_curves import build_regulatory_curve_sets
    from engine.services.nii import compute_nii_margin_set
    from engine.config import NII_HORIZON_MONTHS

    from engine.services.whatif.find_limit import (
        solve_notional_linear,
        solve_binary_search,
        _mutate_spec,
        DEFAULT_BOUNDS,
    )

    _assert_session_exists(session_id)
    t0 = time.perf_counter()

    # 1. Load stored calculation params
    params_file = _calc_params_path(session_id)
    if not params_file.exists():
        raise HTTPException(404, "No base calculation found. Run /calculate first.")
    calc_params = json.loads(params_file.read_text(encoding="utf-8"))

    try:
        analysis_date = date.fromisoformat(calc_params["analysis_date"])
    except (KeyError, ValueError):
        analysis_date = date.today()

    discount_curve_id = calc_params.get("discount_curve_id", "EUR_ESTR_OIS")
    scenarios = calc_params.get("scenarios", [])
    risk_free_index = calc_params.get("risk_free_index", discount_curve_id)
    worst_scenario = calc_params.get("worst_case_scenario", "base")

    # 2. Load stored base results to get current portfolio metric
    from app.session import _results_path
    results_file = _results_path(session_id)
    if not results_file.exists():
        raise HTTPException(404, "No base results found. Run /calculate first.")
    results = json.loads(results_file.read_text(encoding="utf-8"))

    # Resolve target scenario name
    target_sc = req.target_scenario
    if target_sc == "worst":
        target_sc = worst_scenario

    base_metric_value = _resolve_base_metric(results, req.target_metric, req.target_scenario)

    # 3. Build curve sets
    try:
        base_curve_set = _build_forward_curve_set(session_id, analysis_date)
    except Exception as exc:
        raise HTTPException(400, f"Error building curve set: {exc}")

    try:
        scenario_curve_sets = build_regulatory_curve_sets(
            base_set=base_curve_set,
            scenarios=scenarios,
            risk_free_index=risk_free_index,
            currency=calc_params.get("currency", "EUR"),
        )
    except Exception as exc:
        raise HTTPException(400, f"Error building scenario curves: {exc}")

    # Resolve target curve set
    if target_sc == "base":
        target_disc_set = base_curve_set
        target_proj_set = base_curve_set
    else:
        sc_set = scenario_curve_sets.get(target_sc, base_curve_set)
        target_disc_set = sc_set
        target_proj_set = sc_set

    # 4. Convert product spec to LoanSpec
    spec = _loan_spec_from_item(req.product_spec, analysis_date)

    # 5. Pre-calibrate NII margin set (reused for all iterations)
    try:
        # Create a reference DF for margin calibration
        ref_df = decompose_loan(spec)
        if ref_df.empty:
            raise ValueError("Decomposition produced no positions")
        margin_set = compute_nii_margin_set(
            ref_df,
            curve_set=base_curve_set,
            risk_free_index=risk_free_index,
            as_of=base_curve_set.analysis_date,
        )
    except Exception as exc:
        raise HTTPException(500, f"Margin calibration error: {exc}")

    # 6. Build the compute_metric callback
    def compute_metric(df: pd.DataFrame) -> float:
        eve, nii = _compute_eve_nii_scalar(
            df, target_disc_set, target_proj_set,
            discount_curve_id, risk_free_index, margin_set,
            NII_HORIZON_MONTHS,
        )
        return eve if req.target_metric == "eve" else nii

    # 7. Dispatch to solver
    if req.solve_for == "notional":
        result = solve_notional_linear(
            spec, compute_metric, req.limit_value, base_metric_value,
        )
    else:
        bounds = DEFAULT_BOUNDS.get(req.solve_for, (0.0, 100.0))
        result = solve_binary_search(
            spec, compute_metric, req.limit_value, base_metric_value,
            req.solve_for, bounds[0], bounds[1],
        )

    # 8. Build response with solved product_spec
    solved_spec = _mutate_spec(spec, req.solve_for, result.found_value)
    solved_item = LoanSpecItem(
        id=req.product_spec.id,
        notional=solved_spec.notional,
        term_years=solved_spec.term_years,
        side=req.product_spec.side,
        currency=solved_spec.currency,
        rate_type=req.product_spec.rate_type,
        fixed_rate=solved_spec.fixed_rate,
        variable_index=req.product_spec.variable_index,
        spread_bps=solved_spec.spread_bps,
        amortization=req.product_spec.amortization,
        grace_years=req.product_spec.grace_years,
        daycount=req.product_spec.daycount,
        payment_freq=req.product_spec.payment_freq,
        repricing_freq=req.product_spec.repricing_freq,
        start_date=req.product_spec.start_date,
        floor_rate=req.product_spec.floor_rate,
        cap_rate=req.product_spec.cap_rate,
        label=req.product_spec.label,
    )

    return FindLimitResponse(
        session_id=session_id,
        found_value=result.found_value,
        achieved_metric=result.achieved_metric,
        target_metric=req.target_metric,
        target_scenario=req.target_scenario,
        solve_for=req.solve_for,
        converged=result.converged,
        iterations=result.iterations,
        tolerance=result.tolerance,
        product_spec=solved_item,
    )
