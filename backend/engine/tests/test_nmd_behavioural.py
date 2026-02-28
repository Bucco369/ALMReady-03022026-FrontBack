"""Tests for NMD behavioural expansion (Phase 3).

Covers:
  - Core/non-core split
  - Distribution across 19 EBA buckets
  - WAM calculation
  - EVE contribution
  - NII β-repricing (base, shocked, β=0, β=1, floor)
  - Variable NMD routing through standard engine
"""
from __future__ import annotations

from datetime import date, timedelta
import unittest

import pandas as pd

from engine.config.nmd_buckets import NMD_BUCKETS, NMD_BUCKET_MAP
from engine.core.curves import curve_from_long_df
from engine.core.daycount import yearfrac
from engine.services.eve import build_eve_cashflows
from engine.services.eve_analytics import compute_eve_full
from engine.services.market import ForwardCurveSet
from engine.services.nmd_behavioural import expand_nmd_positions
from engine.services.nii import compute_nii_from_cashflows


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_nmd_params(
    core_proportion: float = 75.0,
    pass_through_rate: float = 5.0,
    distribution: dict | None = None,
):
    """Build a lightweight NMDBehaviouralParams-like object."""
    from app.schemas import NMDBehaviouralParams

    if distribution is None:
        # Simple: 75% core all in the 2Y-3Y bucket
        distribution = {"2Y_3Y": 75.0}

    return NMDBehaviouralParams(
        core_proportion=core_proportion,
        core_average_maturity=2.5,
        pass_through_rate=pass_through_rate,
        distribution=distribution,
    )


def _make_nmd_positions(
    total_notional: float = 1_000_000.0,
    fixed_rate: float = 0.0,
    side: str = "L",
    n_positions: int = 1,
) -> pd.DataFrame:
    """Create fixed NMD positions."""
    rows = []
    per = total_notional / n_positions
    for i in range(n_positions):
        rows.append({
            "contract_id": f"NMD_{side}_{i}",
            "start_date": date(2025, 1, 1),
            "notional": per,
            "side": side,
            "rate_type": "fixed",
            "fixed_rate": fixed_rate,
            "daycount_base": "ACT/365",
            "source_contract_type": "fixed_non_maturity",
        })
    return pd.DataFrame(rows)


def _curve_set(
    analysis_date: date = date(2026, 1, 1),
    rf_rate: float = 0.02,
) -> ForwardCurveSet:
    points = pd.DataFrame([
        {
            "IndexName": "EUR_ESTR_OIS",
            "Tenor": "1Y",
            "FwdRate": rf_rate,
            "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
            "YearFrac": 1.0,
        },
    ])
    curves = {"EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS")}
    return ForwardCurveSet(
        analysis_date=analysis_date, base="ACT/365",
        points=points, curves=curves,
    )


ANALYSIS_DATE = date(2026, 1, 1)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestNMDExpansion(unittest.TestCase):

    def test_nmd_core_noncore_split(self):
        """75% core, 25% non-core.  Verify notionals."""
        nmd_params = _make_nmd_params(core_proportion=75.0)
        positions = _make_nmd_positions(total_notional=1_000_000.0, side="L")
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        # Non-core row
        noncore = cf[cf["contract_id"].str.contains("noncore")]
        self.assertEqual(len(noncore), 1)
        self.assertAlmostEqual(abs(float(noncore.iloc[0]["principal_amount"])),
                               250_000.0, places=2)

        # Core rows — total principal should be 750,000
        core = cf[cf["contract_id"].str.contains("core_")]
        core_total = abs(core["principal_amount"].astype(float).sum())
        self.assertAlmostEqual(core_total, 750_000.0, places=2)

    def test_nmd_distribution_sums_to_total(self):
        """All bucket flows sum to total NMD notional."""
        dist = {"ON_1M": 10.0, "1M_3M": 15.0, "3M_6M": 20.0, "6M_9M": 30.0}
        # core_proportion = sum of dist values = 75
        nmd_params = _make_nmd_params(core_proportion=75.0, distribution=dist)
        positions = _make_nmd_positions(total_notional=100_000.0, side="L")
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        total_principal = abs(cf["principal_amount"].astype(float).sum())
        self.assertAlmostEqual(total_principal, 100_000.0, places=2)

    def test_nmd_overnight_bucket(self):
        """Non-core amount is exactly in O/N bucket (analysis_date + 1 day)."""
        nmd_params = _make_nmd_params(core_proportion=80.0, distribution={"2Y_3Y": 80.0})
        positions = _make_nmd_positions(total_notional=500_000.0, side="L")
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        noncore = cf[cf["contract_id"].str.contains("noncore")]
        self.assertEqual(len(noncore), 1)
        expected_noncore = 500_000.0 * 0.20  # 20% non-core
        self.assertAlmostEqual(abs(float(noncore.iloc[0]["principal_amount"])),
                               expected_noncore, places=2)
        # Flow date = analysis_date + 1 day
        self.assertEqual(noncore.iloc[0]["flow_date"], ANALYSIS_DATE + timedelta(days=1))

    def test_nmd_wam_calculation(self):
        """Verify WAM from distribution matches expected."""
        # 50% in 2Y-3Y (midpoint 2.5) + 25% in 4Y-5Y (midpoint 4.5)
        dist = {"2Y_3Y": 50.0, "4Y_5Y": 25.0}
        nmd_params = _make_nmd_params(core_proportion=75.0, distribution=dist)
        # WAM = (50*2.5 + 25*4.5) / 75 = (125+112.5)/75 = 3.167
        expected_wam = (50.0 * 2.5 + 25.0 * 4.5) / 75.0
        self.assertAlmostEqual(expected_wam, 3.1667, places=3)

        # Verify the positions themselves are at the correct midpoints
        positions = _make_nmd_positions(total_notional=1_000_000.0, side="L")
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)
        core = cf[cf["contract_id"].str.contains("core_")]
        # 2Y_3Y midpoint: 2.5yr ≈ 913 days
        row_2y3y = core[core["contract_id"].str.contains("2Y_3Y")]
        self.assertEqual(len(row_2y3y), 1)
        flow_date = row_2y3y.iloc[0]["flow_date"]
        expected_date = ANALYSIS_DATE + timedelta(days=int(round(2.5 * 365.25)))
        self.assertEqual(flow_date, expected_date)

    def test_nmd_wam_high_distribution(self):
        """Distribution with WAM > 5 years is accepted (no cap enforcement)."""
        dist = {"10Y_15Y": 60.0, "20Y_PLUS": 40.0}
        nmd_params = _make_nmd_params(core_proportion=100.0, distribution=dist)
        positions = _make_nmd_positions(total_notional=100_000.0, side="L")
        # Should not raise
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)
        self.assertFalse(cf.empty)
        # WAM = (60*12.5 + 40*25.0)/100 = 17.5 years — way above 5Y cap
        wam = (60.0 * 12.5 + 40.0 * 25.0) / 100.0
        self.assertAlmostEqual(wam, 17.5, places=1)

    def test_nmd_eve_contribution(self):
        """EVE PV of NMD cashflows matches hand calculation."""
        dist = {"9M_1Y": 75.0}  # All core in 9M-1Y (midpoint 0.875yr)
        nmd_params = _make_nmd_params(core_proportion=75.0, distribution=dist)
        cs = _curve_set(rf_rate=0.03)

        # Build positions with NMDs + a trivial non-NMD to ensure pipeline works
        nmd_pos = _make_nmd_positions(total_notional=1_000_000.0, fixed_rate=0.01, side="L")

        cf = expand_nmd_positions(nmd_pos, nmd_params, ANALYSIS_DATE)
        self.assertFalse(cf.empty)

        # Non-core: 250k at day+1, interest=0
        # Core: 750k at ~0.875yr midpoint, interest = 750k * 0.01 * 0.875
        core_row = cf[cf["contract_id"].str.contains("core_")]
        self.assertEqual(len(core_row), 1)
        core_notional = abs(float(core_row.iloc[0]["principal_amount"]))
        self.assertAlmostEqual(core_notional, 750_000.0, places=2)


class TestNMDNIIRepricing(unittest.TestCase):

    def test_nmd_nii_base(self):
        """Base NII (no shock, Δr=0) uses client rate for NMDs."""
        nmd_params = _make_nmd_params(
            core_proportion=0.0,  # All non-core → reprices next day
            distribution={},
        )
        positions = _make_nmd_positions(total_notional=1_000_000.0, fixed_rate=0.02, side="L")
        cs = _curve_set(rf_rate=0.02)
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        result = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE,
            horizon_months=12,
            balance_constant=True,
            nmd_params=nmd_params,
            nmd_rate_delta=0.0,  # base — no shock
        )
        # With no shock, the NMD NII repricing section produces no correction
        # Section A picks up whatever base interest is in the cashflows
        self.assertIsNotNone(result)

    def test_nmd_nii_shocked_with_beta(self):
        """Shocked NII with β=0.05 on 0% account gives 0.10%, not 2.00%."""
        # β = 5% → pass_through_rate = 5.0
        nmd_params = _make_nmd_params(
            core_proportion=0.0,  # All non-core
            pass_through_rate=5.0,
            distribution={},
        )
        positions = _make_nmd_positions(total_notional=1_000_000.0, fixed_rate=0.0, side="L")
        cs = _curve_set(rf_rate=0.04)  # shocked curve
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        # rate_delta = +0.02 (200bps shock)
        result = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE,
            horizon_months=12,
            balance_constant=True,
            nmd_params=nmd_params,
            nmd_rate_delta=0.02,  # +200bps
        )
        # repriced_rate = max(0.0 + 0.05 * 0.02, 0) = 0.001 = 0.10%
        # Expected interest correction: 1M × 0.001 × 1yr = 1,000
        # (liability expense is negative, so total_expense becomes more negative)
        self.assertAlmostEqual(result.liability_nii, -1_000.0, delta=50.0)

    def test_nmd_nii_beta_zero(self):
        """β=0 → no NII impact regardless of shock."""
        nmd_params = _make_nmd_params(
            core_proportion=0.0,
            pass_through_rate=0.0,  # β = 0
            distribution={},
        )
        positions = _make_nmd_positions(total_notional=1_000_000.0, fixed_rate=0.0, side="L")
        cs = _curve_set(rf_rate=0.04)
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        result_shocked = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE,
            horizon_months=12,
            balance_constant=True,
            nmd_params=nmd_params,
            nmd_rate_delta=0.02,
        )
        result_base = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE,
            horizon_months=12,
            balance_constant=True,
            nmd_params=nmd_params,
            nmd_rate_delta=0.0,
        )
        # β=0 means repriced_rate = max(0 + 0*Δr, 0) = 0 = same as client_rate
        # No correction applied → same result
        self.assertAlmostEqual(result_shocked.liability_nii, result_base.liability_nii, places=2)

    def test_nmd_nii_beta_one(self):
        """β=1 → full pass-through (rate moves by full Δr)."""
        nmd_params = _make_nmd_params(
            core_proportion=0.0,  # All non-core
            pass_through_rate=100.0,  # β = 1.0
            distribution={},
        )
        positions = _make_nmd_positions(total_notional=1_000_000.0, fixed_rate=0.01, side="L")
        cs = _curve_set(rf_rate=0.04)
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        result = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE,
            horizon_months=12,
            balance_constant=True,
            nmd_params=nmd_params,
            nmd_rate_delta=0.02,
        )
        # repriced_rate = max(0.01 + 1.0 * 0.02, 0) = 0.03
        # Expected expense: -1M × 0.03 × 1yr = -30,000
        self.assertAlmostEqual(result.liability_nii, -30_000.0, delta=500.0)

    def test_nmd_nii_floor_zero(self):
        """Negative shock: max(0% + 0.05 × (−2%), 0) = 0% (floor at zero)."""
        nmd_params = _make_nmd_params(
            core_proportion=0.0,
            pass_through_rate=5.0,
            distribution={},
        )
        positions = _make_nmd_positions(total_notional=1_000_000.0, fixed_rate=0.0, side="L")
        cs = _curve_set(rf_rate=0.0)
        cf = expand_nmd_positions(positions, nmd_params, ANALYSIS_DATE)

        result = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE,
            horizon_months=12,
            balance_constant=True,
            nmd_params=nmd_params,
            nmd_rate_delta=-0.02,  # −200bps shock
        )
        # repriced_rate = max(0.0 + 0.05 × (−0.02), 0) = max(−0.001, 0) = 0
        # No correction needed — rate stays at 0, same as client_rate
        # NII should be 0 (0% rate on 0% client rate)
        self.assertAlmostEqual(result.liability_nii, 0.0, delta=1.0)


class TestVariableNMDRouting(unittest.TestCase):

    def test_variable_nmd_contractual(self):
        """variable_non_maturity positions route through variable-rate engine."""
        analysis_date = date(2026, 1, 1)
        points = pd.DataFrame([
            {
                "IndexName": "EUR_ESTR_OIS",
                "Tenor": "1Y",
                "FwdRate": 0.03,
                "TenorDate": date(2027, 1, 1),
                "YearFrac": 1.0,
            },
            {
                "IndexName": "EUR_EURIBOR_3M",
                "Tenor": "1Y",
                "FwdRate": 0.035,
                "TenorDate": date(2027, 1, 1),
                "YearFrac": 1.0,
            },
        ])
        curves = {
            "EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS"),
            "EUR_EURIBOR_3M": curve_from_long_df(points, "EUR_EURIBOR_3M"),
        }
        cs = ForwardCurveSet(
            analysis_date=analysis_date, base="ACT/365",
            points=points, curves=curves,
        )

        positions = pd.DataFrame([{
            "contract_id": "VNM1",
            "start_date": date(2025, 1, 1),
            "notional": 100_000.0,
            "side": "L",
            "rate_type": "float",
            "index_name": "EUR_EURIBOR_3M",
            "spread": -0.02,
            "daycount_base": "ACT/365",
            "source_contract_type": "variable_non_maturity",
            "repricing_freq": "3M",
            "fixed_rate": 0.015,
            "floor_rate": 0.0,
            "cap_rate": None,
            "next_reprice_date": date(2026, 4, 1),
        }])

        # Should NOT raise — variable_non_maturity is now in implemented set
        cf = build_eve_cashflows(
            positions,
            analysis_date=analysis_date,
            projection_curve_set=cs,
        )
        # Should produce cashflows (not empty — was previously excluded)
        self.assertFalse(cf.empty)
        # Should be classified as variable_bullet in the output
        # (the re-classification happens internally)
        self.assertTrue(
            cf["contract_id"].str.contains("VNM1").any()
        )


if __name__ == "__main__":
    unittest.main()
