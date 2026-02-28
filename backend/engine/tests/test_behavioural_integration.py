"""Integration tests for behavioural assumptions (Phases 3-5 combined).

Covers:
  - Full EVE+NII calculation with NMD params
  - Full calculation with CPR prepayment
  - All three behavioural assumptions active simultaneously
  - Static position excluded with warning (router-level, simulated here)
  - NMDs without params excluded (only EVE cashflows from maturity instruments)
  - CPR + TDRR applied to correct sides
"""
from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.services.eve import build_eve_cashflows
from engine.services.eve_analytics import compute_eve_full
from engine.services.market import ForwardCurveSet
from engine.services.nii import compute_nii_from_cashflows
from engine.services.nmd_behavioural import expand_nmd_positions


# ── Helpers ────────────────────────────────────────────────────────────────

def _curve_set(
    analysis_date: date = date(2026, 1, 1),
    rf_rate: float = 0.025,
    euribor_rate: float = 0.035,
) -> ForwardCurveSet:
    points = pd.DataFrame([
        {
            "IndexName": "EUR_ESTR_OIS",
            "Tenor": "1Y",
            "FwdRate": rf_rate,
            "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
            "YearFrac": 1.0,
        },
        {
            "IndexName": "EUR_EURIBOR_3M",
            "Tenor": "1Y",
            "FwdRate": euribor_rate,
            "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
            "YearFrac": 1.0,
        },
    ])
    curves = {
        "EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS"),
        "EUR_EURIBOR_3M": curve_from_long_df(points, "EUR_EURIBOR_3M"),
    }
    return ForwardCurveSet(
        analysis_date=analysis_date, base="ACT/365",
        points=points, curves=curves,
    )


def _make_nmd_params(
    core_proportion: float = 75.0,
    pass_through_rate: float = 5.0,
    distribution: dict | None = None,
):
    from app.schemas import NMDBehaviouralParams
    if distribution is None:
        distribution = {"9M_1Y": 40.0, "2Y_3Y": 35.0}
    return NMDBehaviouralParams(
        core_proportion=core_proportion,
        core_average_maturity=2.0,
        pass_through_rate=pass_through_rate,
        distribution=distribution,
    )


ANALYSIS_DATE = date(2026, 1, 1)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestBehaviouralIntegration(unittest.TestCase):

    def test_full_calculation_with_nmd(self):
        """NMD positions included in EVE/NII when behavioural params provided."""
        cs = _curve_set()
        nmd_params = _make_nmd_params()

        # Mix of NMD + standard positions
        positions = pd.DataFrame([
            {
                "contract_id": "LOAN1",
                "start_date": date(2025, 1, 1),
                "maturity_date": date(2027, 6, 1),
                "notional": 200_000.0,
                "side": "A",
                "rate_type": "fixed",
                "fixed_rate": 0.04,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_bullet",
                "payment_freq": "1Y",
            },
            {
                "contract_id": "NMD_DEP1",
                "start_date": date(2024, 1, 1),
                "notional": 500_000.0,
                "side": "L",
                "rate_type": "fixed",
                "fixed_rate": 0.005,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_non_maturity",
            },
        ])

        cf = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE,
            projection_curve_set=cs,
            nmd_params=nmd_params,
        )

        # Should have cashflows from both the loan AND the NMD expansion
        loan_cf = cf[cf["contract_id"] == "LOAN1"]
        nmd_cf = cf[cf["contract_id"].str.startswith("NMD_")]
        self.assertFalse(loan_cf.empty, "Loan should produce cashflows")
        self.assertFalse(nmd_cf.empty, "NMD expansion should produce cashflows")

        # EVE should be computable
        eve, _ = compute_eve_full(
            cf, discount_curve_set=cs, discount_index="EUR_ESTR_OIS",
        )
        self.assertNotEqual(eve, 0.0)

        # NII should be computable
        nii = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE, horizon_months=12,
            nmd_params=nmd_params,
        )
        self.assertNotEqual(nii.aggregate_nii, 0.0)

    def test_full_calculation_with_prepayment(self):
        """End-to-end loan prepayment: CPR reduces interest income.

        Uses quarterly coupons so that multiple interest payments fall within
        the 12M NII horizon — CPR decays the balance, reducing coupons 2-4.
        """
        cs = _curve_set()
        positions = pd.DataFrame([{
            "contract_id": "LOAN1",
            "start_date": date(2025, 1, 1),
            "maturity_date": date(2028, 1, 1),
            "notional": 100_000.0,
            "side": "A",
            "rate_type": "fixed",
            "fixed_rate": 0.05,
            "daycount_base": "ACT/365",
            "source_contract_type": "fixed_bullet",
            "payment_freq": "3M",
        }])

        # Without CPR
        cf_base = build_eve_cashflows(positions, analysis_date=ANALYSIS_DATE)
        nii_base = compute_nii_from_cashflows(
            cf_base, positions, cs,
            analysis_date=ANALYSIS_DATE, horizon_months=12,
        )

        # With CPR=5%
        cf_cpr = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE, cpr_annual=0.05,
        )
        nii_cpr = compute_nii_from_cashflows(
            cf_cpr, positions, cs,
            analysis_date=ANALYSIS_DATE, horizon_months=12,
            cpr_annual=0.05,
        )

        # Prepayment reduces interest income (balance decays → less interest)
        self.assertLess(nii_cpr.asset_nii, nii_base.asset_nii)

    def test_full_calculation_all_behavioural(self):
        """All three active simultaneously: NMD + CPR + TDRR."""
        cs = _curve_set()
        nmd_params = _make_nmd_params()

        positions = pd.DataFrame([
            # Asset loan (gets CPR)
            {
                "contract_id": "LOAN1",
                "start_date": date(2025, 1, 1),
                "maturity_date": date(2028, 1, 1),
                "notional": 100_000.0,
                "side": "A",
                "rate_type": "fixed",
                "fixed_rate": 0.05,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_bullet",
                "payment_freq": "1Y",
            },
            # Term deposit liability (gets TDRR)
            {
                "contract_id": "TD1",
                "start_date": date(2025, 6, 1),
                "maturity_date": date(2027, 6, 1),
                "notional": 80_000.0,
                "side": "L",
                "rate_type": "fixed",
                "fixed_rate": 0.02,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_bullet",
                "payment_freq": "6M",
                "is_term_deposit": True,
            },
            # Fixed NMD (gets NMD behavioural expansion)
            {
                "contract_id": "NMD1",
                "start_date": date(2024, 1, 1),
                "notional": 300_000.0,
                "side": "L",
                "rate_type": "fixed",
                "fixed_rate": 0.001,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_non_maturity",
            },
        ])

        # Build with all behavioural params
        cf = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE,
            projection_curve_set=cs,
            nmd_params=nmd_params,
            cpr_annual=0.05,
            tdrr_annual=0.08,
        )

        # Should have cashflows from all three types
        self.assertFalse(cf.empty)
        # Loan cashflows
        self.assertTrue(cf["contract_id"].str.contains("LOAN1").any())
        # Term deposit cashflows
        self.assertTrue(cf["contract_id"].str.contains("TD1").any())
        # NMD expansion cashflows
        self.assertTrue(cf["contract_id"].str.startswith("NMD_").any())

        # EVE computable
        eve, _ = compute_eve_full(
            cf, discount_curve_set=cs, discount_index="EUR_ESTR_OIS",
        )
        self.assertIsInstance(eve, float)

        # NII computable
        nii = compute_nii_from_cashflows(
            cf, positions, cs,
            analysis_date=ANALYSIS_DATE, horizon_months=12,
            nmd_params=nmd_params,
            cpr_annual=0.05,
            tdrr_annual=0.08,
        )
        self.assertIsInstance(nii.aggregate_nii, float)
        self.assertEqual(len(nii.monthly_breakdown), 12)

    def test_nmd_without_params_excluded(self):
        """NMDs without behavioural params produce no NMD cashflows."""
        cs = _curve_set()
        positions = pd.DataFrame([
            {
                "contract_id": "NMD1",
                "start_date": date(2024, 1, 1),
                "notional": 500_000.0,
                "side": "L",
                "rate_type": "fixed",
                "fixed_rate": 0.0,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_non_maturity",
            },
        ])

        # No nmd_params → fixed_non_maturity is excluded
        cf = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE,
        )
        # Should be empty — NMDs are in _EXCLUDED_SOURCE_CONTRACT_TYPES
        self.assertTrue(cf.empty)

    def test_static_position_excluded(self):
        """static_position rows are excluded from EVE/NII."""
        positions = pd.DataFrame([
            {
                "contract_id": "SP1",
                "start_date": date(2025, 1, 1),
                "maturity_date": date(2030, 1, 1),
                "notional": 999.0,
                "side": "A",
                "rate_type": "fixed",
                "fixed_rate": 0.05,
                "daycount_base": "ACT/365",
                "source_contract_type": "static_position",
            },
        ])
        cf = build_eve_cashflows(positions, analysis_date=ANALYSIS_DATE)
        self.assertTrue(cf.empty)

    def test_cpr_tdrr_side_isolation(self):
        """CPR only affects assets, TDRR only affects term deposit liabilities."""
        cs = _curve_set()

        # Asset + non-TD liability
        positions = pd.DataFrame([
            {
                "contract_id": "ASSET1",
                "start_date": date(2025, 1, 1),
                "maturity_date": date(2028, 1, 1),
                "notional": 100_000.0,
                "side": "A",
                "rate_type": "fixed",
                "fixed_rate": 0.05,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_bullet",
                "payment_freq": "1Y",
                "is_term_deposit": False,
            },
            {
                "contract_id": "LIAB1",
                "start_date": date(2025, 1, 1),
                "maturity_date": date(2028, 1, 1),
                "notional": 80_000.0,
                "side": "L",
                "rate_type": "fixed",
                "fixed_rate": 0.02,
                "daycount_base": "ACT/365",
                "source_contract_type": "fixed_bullet",
                "payment_freq": "1Y",
                "is_term_deposit": False,
            },
        ])

        # With CPR but no TDRR — only asset should be affected
        cf_base = build_eve_cashflows(positions, analysis_date=ANALYSIS_DATE)
        cf_cpr = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE, cpr_annual=0.05,
        )

        # Liability cashflows should be unchanged (not a term deposit, no TDRR)
        liab_base = cf_base[cf_base["contract_id"] == "LIAB1"]
        liab_cpr = cf_cpr[cf_cpr["contract_id"] == "LIAB1"]
        self.assertAlmostEqual(
            float(liab_base["principal_amount"].astype(float).abs().sum()),
            float(liab_cpr["principal_amount"].astype(float).abs().sum()),
            places=2,
        )

        # Asset cashflows should differ (CPR applied)
        asset_base_int = cf_base[cf_base["contract_id"] == "ASSET1"]["interest_amount"].astype(float).sum()
        asset_cpr_int = cf_cpr[cf_cpr["contract_id"] == "ASSET1"]["interest_amount"].astype(float).sum()
        self.assertNotAlmostEqual(float(asset_base_int), float(asset_cpr_int), places=0)


if __name__ == "__main__":
    unittest.main()
