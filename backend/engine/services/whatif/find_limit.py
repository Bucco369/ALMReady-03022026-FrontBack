"""
Find-limit solver: given a product spec and a target metric constraint,
find the value of a single variable (notional/rate/maturity/spread)
that makes the metric reach the specified limit.

For notional: uses linear proportionality (one evaluation + division).
For rate/maturity/spread: binary search over the variable, evaluating
the full decomposer -> EVE/NII pipeline at each iteration.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from engine.services.whatif.decomposer import LoanSpec, decompose_loan


@dataclass
class FindLimitResult:
    found_value: float
    achieved_metric: float
    converged: bool
    iterations: int
    tolerance: float


# ── Internal helpers ──────────────────────────────────────────────────────


def _evaluate_metric(
    spec: LoanSpec,
    compute_metric: Callable[[pd.DataFrame], float],
) -> float:
    """Decompose spec -> run metric computation -> return scalar."""
    df = decompose_loan(spec)
    if df.empty:
        return 0.0
    return compute_metric(df)


def _mutate_spec(spec: LoanSpec, solve_for: str, value: float) -> LoanSpec:
    """Return a copy of spec with the solve_for variable set to value."""
    new_spec = copy.deepcopy(spec)
    if solve_for == "notional":
        new_spec.notional = abs(value)
    elif solve_for == "rate":
        new_spec.fixed_rate = value
    elif solve_for == "maturity":
        new_spec.term_years = max(0.25, value)
    elif solve_for == "spread":
        new_spec.spread_bps = value
    else:
        raise ValueError(f"Unknown solve_for: {solve_for}")
    return new_spec


# ── Solvers ───────────────────────────────────────────────────────────────


def solve_notional_linear(
    spec: LoanSpec,
    compute_metric: Callable[[pd.DataFrame], float],
    limit_value: float,
    base_metric_value: float,
) -> FindLimitResult:
    """For notional: EVE/NII is linear in notional. One evaluation suffices.

    metric(N) = (N / ref_N) * ref_delta
    We want: base_metric + metric(N) = limit_value
    => N = ref_N * (limit_value - base_metric) / ref_delta
    """
    ref_notional = spec.notional
    ref_delta = _evaluate_metric(spec, compute_metric)

    if abs(ref_delta) < 1e-12:
        return FindLimitResult(0.0, base_metric_value, False, 1, float("inf"))

    needed_delta = limit_value - base_metric_value
    found_notional = ref_notional * (needed_delta / ref_delta)

    achieved = base_metric_value + ref_delta * (found_notional / ref_notional)

    return FindLimitResult(
        found_value=max(0, found_notional),
        achieved_metric=achieved,
        converged=True,
        iterations=1,
        tolerance=abs(achieved - limit_value),
    )


def solve_binary_search(
    spec: LoanSpec,
    compute_metric: Callable[[pd.DataFrame], float],
    limit_value: float,
    base_metric_value: float,
    solve_for: str,
    lower: float,
    upper: float,
    max_iterations: int = 30,
    abs_tolerance: float = 1000.0,
) -> FindLimitResult:
    """Binary search over a single variable to hit the target metric."""
    # Evaluate at endpoints to determine monotonicity
    spec_lo = _mutate_spec(spec, solve_for, lower)
    spec_hi = _mutate_spec(spec, solve_for, upper)

    metric_lo = base_metric_value + _evaluate_metric(spec_lo, compute_metric)
    metric_hi = base_metric_value + _evaluate_metric(spec_hi, compute_metric)

    iterations = 2

    # Check if limit is reachable within bounds
    if (metric_lo - limit_value) * (metric_hi - limit_value) > 0:
        # Both endpoints on same side — pick the closer one
        if abs(metric_lo - limit_value) < abs(metric_hi - limit_value):
            return FindLimitResult(lower, metric_lo, False, iterations,
                                   abs(metric_lo - limit_value))
        else:
            return FindLimitResult(upper, metric_hi, False, iterations,
                                   abs(metric_hi - limit_value))

    for _ in range(max_iterations):
        mid = (lower + upper) / 2.0
        spec_mid = _mutate_spec(spec, solve_for, mid)
        metric_mid = base_metric_value + _evaluate_metric(spec_mid, compute_metric)
        iterations += 1

        if abs(metric_mid - limit_value) < abs_tolerance:
            return FindLimitResult(mid, metric_mid, True, iterations,
                                   abs(metric_mid - limit_value))

        # Bisect based on which half contains the root
        if (metric_lo - limit_value) * (metric_mid - limit_value) < 0:
            upper = mid
            metric_hi = metric_mid
        else:
            lower = mid
            metric_lo = metric_mid

    # Max iterations reached — return best estimate
    mid = (lower + upper) / 2.0
    return FindLimitResult(mid, (metric_lo + metric_hi) / 2.0, False, iterations,
                           abs(upper - lower))


# ── Default search bounds ────────────────────────────────────────────────

DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "rate": (0.0, 0.20),          # 0% – 20%
    "maturity": (0.25, 50.0),     # 3 months – 50 years
    "spread": (0.0, 1000.0),      # 0 – 1000 bps
}
