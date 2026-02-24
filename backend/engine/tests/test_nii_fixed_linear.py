from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.core.daycount import normalizar_base_de_calculo, yearfrac
from engine.services.market import ForwardCurveSet
from engine.services.nii import run_nii_12m_scenarios


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


class TestNIIFixedLinear(unittest.TestCase):
    def test_fixed_linear_amortizes_principal_linearly(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(analysis_date)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FL1",
                    "start_date": date(2024, 1, 1),
                    "maturity_date": date(2028, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.04,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_linear",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
        )

        # Remaining life at analysis: 2Y => average outstanding over first year: 75.
        b = normalizar_base_de_calculo("ACT/360")
        yf = yearfrac(date(2026, 1, 1), date(2027, 1, 1), b)
        expected = 75.0 * 0.04 * yf
        self.assertAlmostEqual(out.base_nii_12m, expected, places=10)

    def test_fixed_linear_is_scenario_invariant(self) -> None:
        analysis_date = date(2026, 1, 1)
        base_curve = _curve_set_for_analysis_date(analysis_date)
        up_curve = _curve_set_for_analysis_date(analysis_date)
        down_curve = _curve_set_for_analysis_date(analysis_date)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FL2",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 80.0,
                    "side": "L",
                    "rate_type": "fixed",
                    "fixed_rate": 0.03,
                    "daycount_base": "ACT/365",
                    "source_contract_type": "fixed_linear",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=base_curve,
            scenario_curve_sets={"parallel-up": up_curve, "parallel-down": down_curve},
        )

        self.assertAlmostEqual(out.base_nii_12m, out.scenario_nii_12m["parallel-up"], places=12)
        self.assertAlmostEqual(out.base_nii_12m, out.scenario_nii_12m["parallel-down"], places=12)


if __name__ == "__main__":
    unittest.main()
