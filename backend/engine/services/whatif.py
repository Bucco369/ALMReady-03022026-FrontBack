"""What-If computation service: synthetic rows, delta DataFrames, unified EVE+NII.

Extracted from app/routers/calculate.py to keep financial domain logic in the
engine layer.  The router passes bank-specific config (product templates, index
maps) so this module stays bank-agnostic.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd


# ── Synthetic position creation ────────────────────────────────────────────


def create_synthetic_motor_row(
    mod: Any,
    analysis_date: date,
    *,
    product_templates: dict[str, dict[str, str]],
    category_side_map: dict[str, str],
    freq_to_months: dict[str, int],
    ref_index_to_motor: dict[str, str],
    default_discount_index: str = "EUR_ESTR_OIS",
) -> dict[str, Any]:
    """Build a single motor-compatible row from a What-If modification item.

    *mod* is expected to be a duck-typed object with attributes matching
    ``WhatIfModificationItem`` (id, productTemplateId, category, startDate,
    maturityDate, maturity, rate, spread, refIndex, paymentFreq,
    repricingFreq, notional, currency).
    """
    mapping = product_templates.get(mod.productTemplateId or "", {})
    sct = mapping.get("source_contract_type", "fixed_bullet")
    side = mapping.get("side", category_side_map.get(mod.category or "asset", "A"))

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
        mat = start + timedelta(days=round(mod.maturity * 365.25))

    if mat is None:
        mat = start + timedelta(days=365)

    fixed_rate = mod.rate if mod.rate is not None else 0.0
    spread_val = (mod.spread or 0.0) / 10000.0 if mod.spread else 0.0

    is_variable = "variable" in sct
    raw_ref = (mod.refIndex or "").strip()
    ref_index = ref_index_to_motor.get(raw_ref, raw_ref) or default_discount_index

    freq_str = (mod.paymentFreq or "annual").lower()
    coupon_months = freq_to_months.get(freq_str, 12)

    reprice_str = (mod.repricingFreq or freq_str).lower()
    reprice_months = freq_to_months.get(reprice_str, coupon_months)

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


# ── Delta DataFrame construction ───────────────────────────────────────────


def build_whatif_delta_dataframe(
    modifications: list[Any],
    motor_df: pd.DataFrame,
    balance_rows: list[dict[str, Any]],
    analysis_date: date,
    *,
    product_templates: dict[str, dict[str, str]],
    category_side_map: dict[str, str],
    freq_to_months: dict[str, int],
    ref_index_to_motor: dict[str, str],
    default_discount_index: str = "EUR_ESTR_OIS",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build (add_df, remove_df) from a list of What-If modifications."""
    add_rows: list[dict[str, Any]] = []
    remove_ids: list[str] = []

    for mod in modifications:
        if mod.type == "add":
            add_rows.append(create_synthetic_motor_row(
                mod, analysis_date,
                product_templates=product_templates,
                category_side_map=category_side_map,
                freq_to_months=freq_to_months,
                ref_index_to_motor=ref_index_to_motor,
                default_discount_index=default_discount_index,
            ))

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


# ── Unified EVE+NII computation ────────────────────────────────────────────


def unified_whatif_map(
    df: pd.DataFrame,
    *,
    base_curve_set: Any,
    scenario_curve_sets: dict[str, Any],
    discount_curve_id: str,
    risk_free_index: str,
    horizon_months: int,
) -> tuple[
    dict[tuple[str, str], dict[str, float]],
    dict[str, float],
    dict[tuple[str, int], dict[str, float]],
]:
    """Compute EVE buckets and NII monthly for *df* across base + all scenarios.

    Returns ``(eve_data, eve_meta, nii_data)`` where:
      - *eve_data*: ``{(scenario, bucket_name): {"asset": pv, "liab": pv}}``
      - *eve_meta*: ``{bucket_name: bucket_start_years}``
      - *nii_data*: ``{(scenario, month_index): {"income": ..., "expense": ..., "label": ...}}``
    """
    from engine.services.eve import build_eve_cashflows
    from engine.services.eve_analytics import compute_eve_full
    from engine.services.nii import compute_nii_from_cashflows, compute_nii_margin_set

    eve_data: dict[tuple[str, str], dict[str, float]] = {}
    eve_meta: dict[str, float] = {}
    nii_data: dict[tuple[str, int], dict[str, float]] = {}
    if df.empty:
        return eve_data, eve_meta, nii_data

    margin_set = compute_nii_margin_set(
        df,
        curve_set=base_curve_set,
        risk_free_index=risk_free_index,
        as_of=base_curve_set.analysis_date,
    )

    scenario_items: list[tuple[str, Any, Any]] = [
        ("base", base_curve_set, base_curve_set),
    ]
    for sc_name, sc_set in scenario_curve_sets.items():
        scenario_items.append((sc_name, sc_set, sc_set))

    for sc_label, disc_set, proj_set in scenario_items:
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
            horizon_months=horizon_months,
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

    return eve_data, eve_meta, nii_data
