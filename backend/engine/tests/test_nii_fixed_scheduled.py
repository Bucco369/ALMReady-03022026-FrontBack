from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.core.daycount import normalize_daycount_base, yearfrac
from engine.services.market import ForwardCurveSet
from engine.services.nii import run_nii_12m_base, run_nii_12m_scenarios


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


class TestNIIFixedScheduled(unittest.TestCase):
    def test_fixed_scheduled_uses_principal_flow_path(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(analysis_date)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FS1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.06,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_scheduled",
                }
            ]
        )
        scheduled_flows = pd.DataFrame(
            [
                {"contract_id": "FS1", "flow_date": date(2026, 7, 1), "principal_amount": 40.0},
                {"contract_id": "FS1", "flow_date": date(2027, 1, 1), "principal_amount": 60.0},
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
            scheduled_principal_flows=scheduled_flows,
            balance_constant=False,
        )

        b = normalize_daycount_base("ACT/360")
        expected = (
            100.0 * 0.06 * yearfrac(date(2026, 1, 1), date(2026, 7, 1), b)
            + 60.0 * 0.06 * yearfrac(date(2026, 7, 1), date(2027, 1, 1), b)
        )
        self.assertAlmostEqual(out.base_nii_12m, expected, places=12)

    def test_fixed_scheduled_requires_principal_flows(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(analysis_date)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FS2",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2026, 6, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.05,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_scheduled",
                }
            ]
        )

        with self.assertRaises(ValueError):
            run_nii_12m_base(positions, curve_set)


if __name__ == "__main__":
    unittest.main()
