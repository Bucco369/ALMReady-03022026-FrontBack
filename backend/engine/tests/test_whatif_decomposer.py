"""Tests for the What-If loan decomposer.

Verifies that LoanSpec -> motor-position decomposition produces the
correct number of rows and sensible field values for each combination
of rate_type, amortization, and grace period.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine.services.whatif.decomposer import LoanSpec, decompose_loan


# ── Helpers ──────────────────────────────────────────────────────────────


def _spec(**overrides) -> LoanSpec:
    """Shortcut to build a LoanSpec with sensible defaults."""
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


# ── Position count tests ─────────────────────────────────────────────────


class TestPositionCounts:
    """Each spec shape must produce the expected number of motor rows."""

    def test_fixed_bullet_produces_1_position(self):
        df = decompose_loan(_spec())
        assert len(df) == 1

    def test_fixed_linear_produces_1_position(self):
        df = decompose_loan(_spec(amortization="linear"))
        assert len(df) == 1

    def test_fixed_annuity_produces_1_position(self):
        df = decompose_loan(_spec(amortization="annuity"))
        assert len(df) == 1

    def test_variable_bullet_produces_1_position(self):
        df = decompose_loan(_spec(
            rate_type="variable",
            variable_index="EUR_EURIBOR_12M",
            spread_bps=50,
            fixed_rate=None,
        ))
        assert len(df) == 1

    def test_fixed_linear_grace_produces_3_positions(self):
        df = decompose_loan(_spec(amortization="linear", grace_years=2))
        assert len(df) == 3

    def test_fixed_annuity_grace_produces_3_positions(self):
        df = decompose_loan(_spec(amortization="annuity", grace_years=2))
        assert len(df) == 3

    def test_bullet_with_grace_produces_1_position(self):
        """Grace is irrelevant for bullet — no amortization to defer."""
        df = decompose_loan(_spec(amortization="bullet", grace_years=2))
        assert len(df) == 1

    def test_mixed_bullet_produces_3_positions(self):
        df = decompose_loan(_spec(
            rate_type="mixed",
            mixed_fixed_years=3,
            variable_index="EUR_EURIBOR_12M",
            spread_bps=50,
        ))
        assert len(df) == 3

    def test_mixed_linear_no_grace_produces_3_positions(self):
        """Mixed linear without grace: amort + cancel + var = 3."""
        df = decompose_loan(_spec(
            rate_type="mixed",
            mixed_fixed_years=3,
            amortization="linear",
            variable_index="EUR_EURIBOR_12M",
            spread_bps=50,
        ))
        assert len(df) == 3

    def test_mixed_linear_grace_produces_5_positions(self):
        df = decompose_loan(_spec(
            rate_type="mixed",
            mixed_fixed_years=4,
            amortization="linear",
            grace_years=2,
            variable_index="EUR_EURIBOR_12M",
            spread_bps=50,
            term_years=13,
        ))
        assert len(df) == 5


# ── Field correctness tests ──────────────────────────────────────────────


class TestFieldCorrectness:
    """Verify individual field values on decomposed rows."""

    def test_fixed_bullet_fields(self):
        df = decompose_loan(_spec(notional=5_000_000, fixed_rate=0.025))
        row = df.iloc[0]
        assert row["notional"] == 5_000_000
        assert row["fixed_rate"] == 0.025
        assert row["side"] == "A"
        assert row["source_contract_type"] == "fixed_bullet"
        assert row["currency"] == "EUR"
        assert row["rate_type"] == "fixed"

    def test_variable_has_index_and_spread(self):
        df = decompose_loan(_spec(
            rate_type="variable",
            variable_index="EUR_EURIBOR_6M",
            spread_bps=120,
            fixed_rate=None,
        ))
        row = df.iloc[0]
        assert row["index_name"] == "EUR_EURIBOR_6M"
        assert row["spread"] == pytest.approx(0.012, abs=1e-6)
        assert row["rate_type"] == "float"

    def test_grace_offset_cancels_principal(self):
        """The offset row must be opposite side with zero rate."""
        df = decompose_loan(_spec(amortization="linear", grace_years=2))
        offset = df[df["contract_id"].str.contains("offset")].iloc[0]
        assert offset["side"] == "L"  # opposite of "A"
        assert offset["fixed_rate"] == 0.0
        assert offset["spread"] == 0.0
        assert offset["notional"] == 10_000_000

    def test_floor_cap_passthrough(self):
        df = decompose_loan(_spec(floor_rate=0.005, cap_rate=0.10))
        row = df.iloc[0]
        assert row["floor_rate"] == 0.005
        assert row["cap_rate"] == 0.10

    def test_liability_side(self):
        df = decompose_loan(_spec(side="L"))
        row = df.iloc[0]
        assert row["side"] == "L"

    def test_grace_offset_is_asset_for_liability(self):
        """When main side is L, offset must be A."""
        df = decompose_loan(_spec(side="L", amortization="linear", grace_years=2))
        offset = df[df["contract_id"].str.contains("offset")].iloc[0]
        assert offset["side"] == "A"


# ── Date tests ───────────────────────────────────────────────────────────


class TestDates:
    """Verify start/maturity date derivation."""

    def test_explicit_start_date(self):
        start = date(2026, 6, 1)
        df = decompose_loan(_spec(start_date=start, term_years=10))
        row = df.iloc[0]
        assert row["start_date"] == start
        expected_mat = start + timedelta(days=round(10 * 365.25))
        assert row["maturity_date"] == expected_mat

    def test_grace_end_date(self):
        start = date(2026, 1, 1)
        df = decompose_loan(_spec(
            start_date=start,
            amortization="linear",
            grace_years=2,
            term_years=10,
        ))
        grace_row = df[df["contract_id"].str.contains("grace")].iloc[0]
        expected_grace_end = start + timedelta(days=round(2 * 365.25))
        assert grace_row["maturity_date"] == expected_grace_end

    def test_mixed_switch_date(self):
        """The fixed leg ends at start + mixed_fixed_years."""
        start = date(2026, 1, 1)
        df = decompose_loan(_spec(
            start_date=start,
            rate_type="mixed",
            mixed_fixed_years=3,
            variable_index="EUR_EURIBOR_12M",
            spread_bps=50,
        ))
        fixed_row = df[df["contract_id"].str.contains("fixed")].iloc[0]
        expected_switch = start + timedelta(days=round(3 * 365.25))
        assert fixed_row["maturity_date"] == expected_switch


# ── Schema tests ─────────────────────────────────────────────────────────


class TestSchema:
    """DataFrame must have all required motor columns."""

    REQUIRED_COLUMNS = {
        "contract_id", "side", "source_contract_type", "notional",
        "fixed_rate", "spread", "start_date", "maturity_date",
        "index_name", "next_reprice_date", "daycount_base",
        "payment_freq", "repricing_freq", "currency",
        "floor_rate", "cap_rate", "rate_type",
    }

    def test_all_columns_present(self):
        df = decompose_loan(_spec())
        assert self.REQUIRED_COLUMNS.issubset(set(df.columns))

    def test_mixed_all_columns_present(self):
        df = decompose_loan(_spec(
            rate_type="mixed",
            mixed_fixed_years=3,
            variable_index="EUR_EURIBOR_12M",
        ))
        assert self.REQUIRED_COLUMNS.issubset(set(df.columns))


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_mixed_requires_mixed_fixed_years(self):
        with pytest.raises(ValueError, match="mixed_fixed_years"):
            decompose_loan(_spec(rate_type="mixed", mixed_fixed_years=None))

    def test_zero_notional(self):
        df = decompose_loan(_spec(notional=0))
        assert len(df) == 1
        assert df.iloc[0]["notional"] == 0

    def test_very_short_term(self):
        df = decompose_loan(_spec(term_years=0.25))
        assert len(df) == 1

    def test_id_prefix_propagates(self):
        df = decompose_loan(_spec(id_prefix="test123"))
        for cid in df["contract_id"]:
            assert cid.startswith("test123")
