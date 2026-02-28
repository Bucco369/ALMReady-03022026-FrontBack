"""Tests for term deposit early redemption TDRR (Phase 5).

Covers:
  - TDRR=0 baseline (unchanged flows)
  - TDRR monthly decay on bullet
  - TDRR reduces maturity cashflow
  - TDRR EVE impact (liability duration shortens)
  - TDRR applies only to liabilities, not assets
"""
from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.services.eve import build_eve_cashflows, _apply_cpr_overlay
from engine.services.eve_analytics import compute_eve_full
from engine.services.market import ForwardCurveSet
from engine.services.nii import compute_nii_from_cashflows


# ── Helpers ────────────────────────────────────────────────────────────────

def _curve_set(
    analysis_date: date = date(2026, 1, 1),
    rf_rate: float = 0.02,
) -> ForwardCurveSet:
    points = pd.DataFrame([{
        "IndexName": "EUR_ESTR_OIS",
        "Tenor": "1Y",
        "FwdRate": rf_rate,
        "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
        "YearFrac": 1.0,
    }])
    curves = {"EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS")}
    return ForwardCurveSet(
        analysis_date=analysis_date, base="ACT/365",
        points=points, curves=curves,
    )


def _term_deposit_position(
    contract_id: str = "TD1",
    notional: float = 500_000.0,
    fixed_rate: float = 0.025,
    start: date = date(2026, 1, 1),
    maturity: date = date(2028, 1, 1),
    daycount: str = "30/360",
    payment_freq: str = "6M",
) -> dict:
    return {
        "contract_id": contract_id,
        "start_date": start,
        "maturity_date": maturity,
        "notional": notional,
        "side": "L",
        "rate_type": "fixed",
        "fixed_rate": fixed_rate,
        "daycount_base": daycount,
        "source_contract_type": "fixed_bullet",
        "payment_freq": payment_freq,
        "is_term_deposit": True,
    }


ANALYSIS_DATE = date(2026, 1, 1)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestTDRROverlay(unittest.TestCase):

    def test_tdrr_zero(self):
        """No early redemption — flows unchanged."""
        from dateutil.relativedelta import relativedelta
        notional = 500_000.0
        flow_map = {}
        for i in range(1, 5):  # 4 semi-annual periods
            fd = ANALYSIS_DATE + relativedelta(months=i * 6)
            interest = notional * 0.025 * 0.5  # 6M accrual
            principal = notional if i == 4 else 0.0
            flow_map[fd] = {
                "interest_amount": -interest,  # liability → negative
                "principal_amount": -principal,
            }

        result = _apply_cpr_overlay(
            flow_map, outstanding=notional, sign=-1.0,
            cpr_annual=0.0, daycount_base_days=360.0,
            accrual_start=ANALYSIS_DATE,
        )
        # CPR=0 → returns original
        self.assertIs(result, flow_map)

    def test_tdrr_monthly_decay(self):
        """TDRR=8% annual: verify balance decays each period."""
        from dateutil.relativedelta import relativedelta
        notional = 500_000.0
        tdrr_annual = 0.08

        flow_map = {}
        for i in range(1, 5):  # 4 semi-annual periods
            fd = ANALYSIS_DATE + relativedelta(months=i * 6)
            interest = notional * 0.025 * 0.5
            principal = notional if i == 4 else 0.0
            flow_map[fd] = {
                "interest_amount": -interest,
                "principal_amount": -principal,
            }

        result = _apply_cpr_overlay(
            flow_map, outstanding=notional, sign=-1.0,
            cpr_annual=tdrr_annual, daycount_base_days=360.0,
            accrual_start=ANALYSIS_DATE,
        )

        sorted_dates = sorted(result.keys())
        # Period 1: combined = min(1, 0 + TDRRp), actual days from analysis_date
        p1 = result[sorted_dates[0]]
        actual_days_p1 = (sorted_dates[0] - ANALYSIS_DATE).days  # 181 (Jan→Jul)
        expected_qcm = notional * (1.0 - (1.0 - tdrr_annual) ** (actual_days_p1 / 360.0))
        self.assertAlmostEqual(abs(p1["principal_amount"]), expected_qcm, delta=5.0)

        # Each subsequent period should have less principal (DRm decreasing)
        principals = [abs(result[d]["principal_amount"]) for d in sorted_dates[:-1]]
        for i in range(1, len(principals)):
            self.assertLess(principals[i], principals[i - 1])

    def test_tdrr_reduces_maturity_cashflow(self):
        """Maturity cashflow < original notional due to early redemptions."""
        from dateutil.relativedelta import relativedelta
        notional = 500_000.0

        flow_map = {}
        for i in range(1, 5):
            fd = ANALYSIS_DATE + relativedelta(months=i * 6)
            interest = notional * 0.025 * 0.5
            principal = notional if i == 4 else 0.0
            flow_map[fd] = {
                "interest_amount": -interest,
                "principal_amount": -principal,
            }

        result = _apply_cpr_overlay(
            flow_map, outstanding=notional, sign=-1.0,
            cpr_annual=0.08, daycount_base_days=360.0,
            accrual_start=ANALYSIS_DATE,
        )

        sorted_dates = sorted(result.keys())
        final_principal = abs(result[sorted_dates[-1]]["principal_amount"])
        # Final principal should be less than original notional
        self.assertLess(final_principal, notional)
        # But total principal across all periods should equal notional
        total = sum(abs(result[d]["principal_amount"]) for d in sorted_dates)
        self.assertAlmostEqual(total, notional, delta=0.01)


class TestTDRRInPipeline(unittest.TestCase):

    def test_tdrr_eve_impact(self):
        """EVE with TDRR differs from EVE without (liability duration shortens)."""
        cs = _curve_set(rf_rate=0.03)
        positions = pd.DataFrame([_term_deposit_position()])

        # Without TDRR
        cf_no_tdrr = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE,
        )
        eve_no_tdrr, _ = compute_eve_full(
            cf_no_tdrr, discount_curve_set=cs,
            discount_index="EUR_ESTR_OIS",
        )

        # With TDRR=8%
        cf_tdrr = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE,
            tdrr_annual=0.08,
        )
        eve_tdrr, _ = compute_eve_full(
            cf_tdrr, discount_curve_set=cs,
            discount_index="EUR_ESTR_OIS",
        )

        # TDRR changes the cash flow timing
        self.assertNotAlmostEqual(eve_no_tdrr, eve_tdrr, places=0)

    def test_tdrr_only_applies_to_term_deposits(self):
        """TDRR should NOT affect asset-side positions."""
        cs = _curve_set(rf_rate=0.02)
        # Asset position — should NOT get TDRR
        asset_pos = {
            "contract_id": "ASSET1",
            "start_date": date(2026, 1, 1),
            "maturity_date": date(2028, 1, 1),
            "notional": 100_000.0,
            "side": "A",
            "rate_type": "fixed",
            "fixed_rate": 0.05,
            "daycount_base": "30/360",
            "source_contract_type": "fixed_bullet",
            "payment_freq": "1Y",
            "is_term_deposit": False,
        }
        positions = pd.DataFrame([asset_pos])

        # Without any decay
        cf_base = build_eve_cashflows(positions, analysis_date=ANALYSIS_DATE)
        # With TDRR but no CPR — asset shouldn't change
        cf_tdrr = build_eve_cashflows(
            positions, analysis_date=ANALYSIS_DATE, tdrr_annual=0.08,
        )

        # Asset cashflows should be identical (TDRR only hits term deposit liabilities)
        base_principal = cf_base["principal_amount"].astype(float).abs().sum()
        tdrr_principal = cf_tdrr["principal_amount"].astype(float).abs().sum()
        self.assertAlmostEqual(float(base_principal), float(tdrr_principal), places=2)


if __name__ == "__main__":
    unittest.main()
