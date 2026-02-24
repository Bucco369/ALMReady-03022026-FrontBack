from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.services.market import ForwardCurveSet
from engine.services.nii import build_nii_monthly_profile, run_nii_12m_base


def _curve_set_for_analysis_date(analysis_date: date) -> ForwardCurveSet:
    points = pd.DataFrame(
        [
            {
                "IndexName": "EUR_ESTR_OIS",
                "Tenor": "1Y",
                "FwdRate": 0.02,
                "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
                "YearFrac": 1.0,
            }
        ]
    )
    curves = {"EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS")}
    return ForwardCurveSet(
        analysis_date=analysis_date,
        base="ACT/365",
        points=points,
        curves=curves,
    )


class TestNIIMonthlyProfile(unittest.TestCase):
    def test_monthly_profile_matches_12m_total_without_rollover(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(analysis_date)
        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FBM1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.06,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_bullet",
                },
                {
                    "contract_id": "LBL1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 50.0,
                    "side": "L",
                    "rate_type": "fixed",
                    "fixed_rate": 0.02,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_bullet",
                },
            ]
        )

        monthly = build_nii_monthly_profile(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
            balance_constant=False,
            months=12,
        )

        self.assertEqual(sorted(monthly["scenario"].unique().tolist()), ["base"])
        self.assertEqual(len(monthly), 12)

        total_from_monthly = float(monthly["net_nii"].sum())
        total_direct = run_nii_12m_base(
            positions,
            curve_set,
            balance_constant=False,
            horizon_months=12,
        )
        self.assertAlmostEqual(total_from_monthly, total_direct, places=10)

        income_sum = float(monthly["interest_income"].sum())
        expense_sum = float(monthly["interest_expense"].sum())
        self.assertGreater(income_sum, 0.0)
        self.assertLess(expense_sum, 0.0)


if __name__ == "__main__":
    unittest.main()

