from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.core.daycount import normalizar_base_de_calculo, yearfrac
from engine.services.market import ForwardCurveSet
from engine.services.nii import run_nii_12m_scenarios


def _curve_set_for_analysis_date(analysis_date: date, rf_1y: float = 0.02) -> ForwardCurveSet:
    points = pd.DataFrame(
        [
            {
                "IndexName": "EUR_ESTR_OIS",
                "Tenor": "1Y",
                "FwdRate": float(rf_1y),
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


class TestNIIFixedAnnuity(unittest.TestCase):
    def test_fixed_annuity_matches_french_style_interest(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(analysis_date, rf_1y=0.02)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FA1",
                    "start_date": date(2026, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.06,
                    "daycount_base": "ACT/360",
                    "payment_freq": "6M",
                    "source_contract_type": "fixed_annuity",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
        )

        b = normalizar_base_de_calculo("ACT/360")
        d0 = date(2026, 1, 1)
        d1 = date(2026, 7, 1)
        d2 = date(2027, 1, 1)
        yf1 = yearfrac(d0, d1, b)
        yf2 = yearfrac(d1, d2, b)
        r = 0.06
        n0 = 100.0

        f1 = 1.0 + r * yf1
        f2 = 1.0 + r * yf2
        payment = n0 / (1.0 / f1 + 1.0 / (f1 * f2))

        interest1 = n0 * r * yf1
        principal1 = payment - interest1
        n1 = n0 - principal1
        interest2 = n1 * r * yf2
        expected = interest1 + interest2

        self.assertAlmostEqual(out.base_nii_12m, expected, places=10)

    def test_fixed_annuity_rollover_is_scenario_sensitive(self) -> None:
        analysis_date = date(2026, 1, 1)
        base_curve = _curve_set_for_analysis_date(analysis_date, rf_1y=0.02)
        up_curve = _curve_set_for_analysis_date(analysis_date, rf_1y=0.04)
        down_curve = _curve_set_for_analysis_date(analysis_date, rf_1y=0.00)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FA2",
                    "start_date": date(2025, 7, 1),
                    "maturity_date": date(2026, 4, 1),  # vence dentro de horizonte
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.05,
                    "daycount_base": "ACT/360",
                    "payment_freq": "1M",
                    "source_contract_type": "fixed_annuity",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=base_curve,
            scenario_curve_sets={"parallel-up": up_curve, "parallel-down": down_curve},
        )

        self.assertGreater(out.scenario_nii_12m["parallel-up"], out.base_nii_12m)
        self.assertLess(out.scenario_nii_12m["parallel-down"], out.base_nii_12m)


if __name__ == "__main__":
    unittest.main()
