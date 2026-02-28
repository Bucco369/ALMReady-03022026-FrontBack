"""Tests for the What-If find-limit solver.

Tests the binary search and linear solvers in isolation using
deterministic mock metric functions (no full EVE/NII pipeline).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from engine.services.whatif.decomposer import LoanSpec
from engine.services.whatif.find_limit import (
    DEFAULT_BOUNDS,
    FindLimitResult,
    solve_binary_search,
    solve_notional_linear,
    _mutate_spec,
    _evaluate_metric,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _spec(**overrides) -> LoanSpec:
    defaults = dict(
        notional=10_000_000,
        term_years=5,
        side="A",
        currency="EUR",
        rate_type="fixed",
        fixed_rate=0.03,
        amortization="bullet",
        daycount="30/360",
        payment_freq="12M",
        start_date=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return LoanSpec(**defaults)


def _metric_sum_notional(df: pd.DataFrame) -> float:
    """Toy metric: sum of notional column (linear in notional)."""
    return df["notional"].sum()


def _metric_weighted_rate(df: pd.DataFrame) -> float:
    """Toy metric: notional-weighted fixed rate (depends on rate non-linearly via decomposer)."""
    total = df["notional"].sum()
    if total == 0:
        return 0.0
    return (df["notional"] * df["fixed_rate"]).sum() / total


# ── _mutate_spec tests ──────────────────────────────────────────────────


class TestMutateSpec:
    def test_mutate_notional(self):
        spec = _spec()
        new = _mutate_spec(spec, "notional", 5_000_000)
        assert new.notional == 5_000_000
        assert spec.notional == 10_000_000  # original unchanged

    def test_mutate_rate(self):
        new = _mutate_spec(_spec(), "rate", 0.05)
        assert new.fixed_rate == 0.05

    def test_mutate_maturity(self):
        new = _mutate_spec(_spec(), "maturity", 10)
        assert new.term_years == 10

    def test_mutate_maturity_clamps_minimum(self):
        new = _mutate_spec(_spec(), "maturity", 0.1)
        assert new.term_years == 0.25  # clamped

    def test_mutate_spread(self):
        new = _mutate_spec(_spec(), "spread", 150)
        assert new.spread_bps == 150

    def test_mutate_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown solve_for"):
            _mutate_spec(_spec(), "unknown_field", 1.0)


# ── _evaluate_metric tests ──────────────────────────────────────────────


class TestEvaluateMetric:
    def test_evaluate_returns_scalar(self):
        spec = _spec()
        result = _evaluate_metric(spec, _metric_sum_notional)
        assert result == pytest.approx(10_000_000)

    def test_evaluate_empty_spec(self):
        """Zero notional still produces a row; metric returns 0."""
        spec = _spec(notional=0)
        result = _evaluate_metric(spec, _metric_sum_notional)
        assert result == 0.0


# ── solve_notional_linear tests ─────────────────────────────────────────


class TestSolveNotionalLinear:
    def test_basic_linear_solve(self):
        """If metric is proportional to notional, solver should find exact answer."""
        spec = _spec(notional=1_000_000)
        # Metric at reference = 1M. We want base + delta = 5M, base = 0.
        result = solve_notional_linear(
            spec,
            _metric_sum_notional,
            limit_value=5_000_000,
            base_metric_value=0,
        )
        assert isinstance(result, FindLimitResult)
        assert result.converged is True
        assert result.iterations == 1
        assert result.found_value == pytest.approx(5_000_000, rel=1e-6)

    def test_linear_solve_with_base(self):
        """With a non-zero base, need delta = limit - base."""
        spec = _spec(notional=1_000_000)
        result = solve_notional_linear(
            spec,
            _metric_sum_notional,
            limit_value=3_000_000,
            base_metric_value=1_000_000,
        )
        assert result.converged is True
        # Need 2M delta, ref gives 1M per 1M notional → need 2M notional
        assert result.found_value == pytest.approx(2_000_000, rel=1e-6)

    def test_linear_solve_zero_delta(self):
        """If ref_delta ≈ 0, solver cannot converge."""
        spec = _spec(notional=0)
        result = solve_notional_linear(
            spec,
            _metric_sum_notional,
            limit_value=1_000_000,
            base_metric_value=0,
        )
        assert result.converged is False
        assert result.found_value == 0.0

    def test_negative_notional_clamped(self):
        """Found notional should not be negative."""
        spec = _spec(notional=1_000_000)
        result = solve_notional_linear(
            spec,
            _metric_sum_notional,
            limit_value=-2_000_000,
            base_metric_value=0,
        )
        assert result.found_value >= 0


# ── solve_binary_search tests ───────────────────────────────────────────


class TestSolveBinarySearch:
    def test_rate_search_converges(self):
        """Binary search for rate on a simple metric should converge."""
        spec = _spec(notional=10_000_000)

        # Metric: notional * fixed_rate (monotonically increasing in rate)
        def metric(df: pd.DataFrame) -> float:
            return (df["notional"] * df["fixed_rate"]).sum()

        # Base metric = 0, want metric = 500_000 → rate should be ~0.05
        result = solve_binary_search(
            spec,
            metric,
            limit_value=500_000,
            base_metric_value=0,
            solve_for="rate",
            lower=0.0,
            upper=0.20,
            abs_tolerance=100,
        )
        assert result.converged is True
        assert result.found_value == pytest.approx(0.05, abs=0.001)

    def test_maturity_search_converges(self):
        """Search for maturity."""
        spec = _spec(notional=1_000_000, fixed_rate=0.03)

        # Metric proportional to term_years (via longer maturity → more positions for non-bullet)
        # For bullet: single position, metric just uses fixed_rate × notional regardless of maturity
        # Use a metric that depends on maturity: count of days to maturity
        def metric(df: pd.DataFrame) -> float:
            days = [(mat - st).days for mat, st in zip(df["maturity_date"], df["start_date"])]
            return sum(days)

        result = solve_binary_search(
            spec,
            metric,
            limit_value=3652,  # ~10 years in days
            base_metric_value=0,
            solve_for="maturity",
            lower=1.0,
            upper=20.0,
            abs_tolerance=30,  # ~1 month tolerance
        )
        assert result.converged is True
        assert result.found_value == pytest.approx(10, abs=0.5)

    def test_search_unreachable_returns_closest(self):
        """If limit is outside the [lo, hi] metric range, return closest."""
        spec = _spec(notional=1_000_000)

        def metric(df: pd.DataFrame) -> float:
            return df["notional"].sum()

        # Limit way beyond what 0-20% rate changes could affect for notional metric
        result = solve_binary_search(
            spec,
            metric,
            limit_value=999_999_999,
            base_metric_value=0,
            solve_for="rate",
            lower=0.0,
            upper=0.20,
        )
        assert result.converged is False

    def test_search_respects_max_iterations(self):
        spec = _spec()

        def metric(df: pd.DataFrame) -> float:
            return (df["notional"] * df["fixed_rate"]).sum()

        result = solve_binary_search(
            spec,
            metric,
            limit_value=250_000,
            base_metric_value=0,
            solve_for="rate",
            lower=0.0,
            upper=0.20,
            max_iterations=3,
            abs_tolerance=1,  # very tight — won't converge in 3 iters
        )
        # 2 endpoint evals + 3 mid evals = 5
        assert result.iterations <= 5


# ── DEFAULT_BOUNDS tests ────────────────────────────────────────────────


class TestDefaultBounds:
    def test_rate_bounds(self):
        lo, hi = DEFAULT_BOUNDS["rate"]
        assert lo == 0.0
        assert hi == 0.20

    def test_maturity_bounds(self):
        lo, hi = DEFAULT_BOUNDS["maturity"]
        assert lo == 0.25
        assert hi == 50.0

    def test_spread_bounds(self):
        lo, hi = DEFAULT_BOUNDS["spread"]
        assert lo == 0.0
        assert hi == 1000.0
