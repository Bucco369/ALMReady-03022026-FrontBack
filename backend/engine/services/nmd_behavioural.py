"""
NMD behavioural expansion: convert fixed NMD positions into synthetic
cash-flow records slotted across the 19 EBA time buckets.

Variable NMDs (variable_non_maturity) are NOT handled here — they go
through the standard variable-rate engine.  See §2.5 of the plan.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from engine.config.nmd_buckets import NMD_BUCKET_MAP
from engine.core.daycount import yearfrac


def expand_nmd_positions(
    nmd_positions: pd.DataFrame,
    nmd_params,  # NMDBehaviouralParams (imported lazily to avoid circular ref)
    analysis_date: date,
) -> pd.DataFrame:
    """
    Convert fixed-NMD positions into synthetic EVE cashflow records
    distributed across core / non-core buckets.

    Parameters
    ----------
    nmd_positions : DataFrame
        Rows with source_contract_type == "fixed_non_maturity".
        Must contain: contract_id, notional, side, fixed_rate.
    nmd_params : NMDBehaviouralParams
        core_proportion (0-100 %), distribution (bucket_id → %),
        pass_through_rate (0-100 %), etc.
    analysis_date : date
        As-of date for the calculation.

    Returns
    -------
    DataFrame
        Cashflow records with columns: contract_id, source_contract_type,
        rate_type, side, flow_date, interest_amount, principal_amount,
        total_amount, index_name.
    """
    if nmd_positions.empty:
        return pd.DataFrame()

    records: list[dict] = []

    # ── Aggregate per side ──────────────────────────────────────────────
    for side_val in ("A", "L"):
        side_col = nmd_positions["side"].astype(str).str.strip().str.upper()
        side_mask = side_col.eq(side_val)
        side_df = nmd_positions.loc[side_mask]
        if side_df.empty:
            continue

        notionals = side_df["notional"].astype(float)
        total_notional = float(notionals.sum())
        if abs(total_notional) < 1e-10:
            continue

        # Weighted-average client rate
        rates = side_df["fixed_rate"].astype(float)
        avg_rate = float((rates * notionals).sum() / total_notional)

        sign = 1.0 if side_val == "A" else -1.0
        core_frac = nmd_params.core_proportion / 100.0
        noncore_frac = 1.0 - core_frac

        # ── Non-core: overnight bucket ──────────────────────────────────
        noncore_notional = total_notional * noncore_frac
        if abs(noncore_notional) > 1e-10:
            on_date = analysis_date + timedelta(days=1)
            records.append({
                "contract_id": f"NMD_{side_val}_noncore",
                "source_contract_type": "fixed_non_maturity",
                "rate_type": "fixed",
                "side": side_val,
                "flow_date": on_date,
                "interest_amount": 0.0,  # reprices next day via β
                "principal_amount": sign * noncore_notional,
                "total_amount": sign * noncore_notional,
                "index_name": None,
            })

        # ── Core: distributed across EBA buckets ────────────────────────
        distribution = nmd_params.distribution  # bucket_id → % of total
        for bucket_id, weight_pct in distribution.items():
            if weight_pct <= 0.0:
                continue
            bucket = NMD_BUCKET_MAP.get(bucket_id)
            if bucket is None:
                continue
            # Skip O/N in the distribution — non-core handles it
            if bucket_id == "ON":
                continue

            notional_k = total_notional * (weight_pct / 100.0)
            if abs(notional_k) < 1e-10:
                continue

            midpoint_days = int(round(bucket.midpoint_years * 365.25))
            flow_date_k = analysis_date + timedelta(days=midpoint_days)

            # Interest accrued from analysis_date to flow_date
            yf = yearfrac(analysis_date, flow_date_k, "ACT/365")
            interest_k = notional_k * avg_rate * yf

            records.append({
                "contract_id": f"NMD_{side_val}_core_{bucket_id}",
                "source_contract_type": "fixed_non_maturity",
                "rate_type": "fixed",
                "side": side_val,
                "flow_date": flow_date_k,
                "interest_amount": sign * interest_k,
                "principal_amount": sign * notional_k,
                "total_amount": sign * (interest_k + notional_k),
                "index_name": None,
            })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)
