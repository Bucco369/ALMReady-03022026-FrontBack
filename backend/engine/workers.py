"""
Picklable worker functions for ProcessPoolExecutor.

Defined at module level in a dedicated module (NOT in app/main.py) so that
child processes only import this lightweight file, not the full FastAPI app
(which would re-run app = FastAPI(), add_middleware, etc. on every spawn).

Lazy imports inside each function (from engine.services.xxx import ...) are
intentional: they populate sys.modules in the worker process so that
subsequent calls in the same worker are instant (cache hit).
"""
from __future__ import annotations

import pandas as pd


def warmup() -> None:
    """
    Pre-import the heavy engine modules so that subsequent task calls
    in this worker process incur zero import overhead.
    Called once per worker during server startup (lifespan).
    """
    import engine.services.eve          # noqa: F401
    import engine.services.eve_analytics  # noqa: F401
    import engine.services.nii          # noqa: F401
    import engine.services.nii_projectors  # noqa: F401


def eve_base(
    positions: pd.DataFrame,
    discount_curve_set,
    projection_curve_set,
    discount_index: str,
    method: str,
) -> float:
    """Compute EVE for one curve set (base or a stressed scenario)."""
    from engine.services.eve import run_eve_base

    return run_eve_base(
        positions,
        discount_curve_set,
        projection_curve_set=projection_curve_set,
        discount_index=discount_index,
        method=method,
    )


def nii_base(
    positions: pd.DataFrame,
    curve_set,
    margin_set,
    risk_free_index: str,
    balance_constant: bool,
    horizon_months: int,
    variable_annuity_payment_mode: str,
) -> float:
    """Compute NII-12m for one curve set (base or a stressed scenario)."""
    from engine.services.nii import run_nii_12m_base

    return run_nii_12m_base(
        positions,
        curve_set,
        margin_set=margin_set,
        risk_free_index=risk_free_index,
        balance_constant=balance_constant,
        horizon_months=horizon_months,
        variable_annuity_payment_mode=variable_annuity_payment_mode,
    )


def eve_nii_unified(
    positions: pd.DataFrame,
    discount_curve_set,
    projection_curve_set,
    discount_index: str,
    margin_set,
    risk_free_index: str,
    balance_constant: bool,
    horizon_months: int,
    scheduled_principal_flows=None,
) -> dict:
    """Unified worker: build cashflows ONCE, derive both EVE and NII.

    Returns a serializable dict with:
      eve_scalar, eve_buckets, nii_scalar, nii_asset, nii_liability, nii_monthly
    """
    from engine.services.eve import build_eve_cashflows
    from engine.services.eve_analytics import compute_eve_full
    from engine.services.nii import compute_nii_from_cashflows

    analysis_date = discount_curve_set.analysis_date

    # 1. Build cashflows ONCE
    cashflows = build_eve_cashflows(
        positions,
        analysis_date=analysis_date,
        projection_curve_set=projection_curve_set,
        scheduled_principal_flows=scheduled_principal_flows,
    )

    # 2. EVE: scalar + bucket breakdown from the same cashflows
    eve_scalar, eve_buckets = compute_eve_full(
        cashflows,
        discount_curve_set=discount_curve_set,
        discount_index=discount_index,
        include_buckets=True,
    )

    # 3. NII: aggregate + monthly from the same cashflows
    nii_result = compute_nii_from_cashflows(
        cashflows,
        positions,
        projection_curve_set,
        analysis_date=analysis_date,
        horizon_months=horizon_months,
        balance_constant=balance_constant,
        margin_set=margin_set,
        risk_free_index=risk_free_index,
        scheduled_principal_flows=scheduled_principal_flows,
    )

    return {
        "eve_scalar": eve_scalar,
        "eve_buckets": eve_buckets,
        "nii_scalar": nii_result.aggregate_nii,
        "nii_asset": nii_result.asset_nii,
        "nii_liability": nii_result.liability_nii,
        "nii_monthly": nii_result.monthly_breakdown,
    }
