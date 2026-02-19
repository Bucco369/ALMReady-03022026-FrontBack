"""
Picklable worker functions for ProcessPoolExecutor.

Defined at module level in a dedicated module (NOT in app/main.py) so that
child processes only import this lightweight file, not the full FastAPI app
(which would re-run app = FastAPI(), add_middleware, etc. on every spawn).

Lazy imports inside each function (from almready.services.xxx import ...) are
intentional: they populate sys.modules in the worker process so that
subsequent calls in the same worker are instant (cache hit).
"""
from __future__ import annotations

import pandas as pd


def warmup() -> None:
    """
    Pre-import the heavy almready modules so that subsequent task calls
    in this worker process incur zero import overhead.
    Called once per worker during server startup (lifespan).
    """
    import almready.services.eve          # noqa: F401
    import almready.services.nii          # noqa: F401
    import almready.services.nii_projectors  # noqa: F401


def eve_base(
    positions: pd.DataFrame,
    discount_curve_set,
    projection_curve_set,
    discount_index: str,
    method: str,
) -> float:
    """Compute EVE for one curve set (base or a stressed scenario)."""
    from almready.services.eve import run_eve_base

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
    from almready.services.nii import run_nii_12m_base

    return run_nii_12m_base(
        positions,
        curve_set,
        margin_set=margin_set,
        risk_free_index=risk_free_index,
        balance_constant=balance_constant,
        horizon_months=horizon_months,
        variable_annuity_payment_mode=variable_annuity_payment_mode,
    )
