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


class TestNIIFixedBullet(unittest.TestCase):
    def test_run_nii_12m_base_fixed_bullet(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(analysis_date)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "A1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2028, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.05,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_bullet",
                },
                {
                    "contract_id": "L1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2026, 7, 1),
                    "notional": 80.0,
                    "side": "L",
                    "rate_type": "fixed",
                    "fixed_rate": 0.03,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_bullet",
                },
                {
                    "contract_id": "A2",
                    "start_date": date(2026, 10, 1),
                    "maturity_date": date(2027, 6, 1),
                    "notional": 50.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.04,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_bullet",
                },
                # Excluded due to static_position.
                {
                    "contract_id": "S1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2030, 1, 1),
                    "notional": 999.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.99,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "static_position",
                },
            ]
        )

        b = normalize_daycount_base("ACT/360")
        expected = 0.0
        expected += 100.0 * 0.05 * yearfrac(date(2026, 1, 1), date(2027, 1, 1), b)
        # Constant balance: L1 matures on 2026-07-01 and rolls over for the rest of the horizon.
        expected += -80.0 * 0.03 * yearfrac(date(2026, 1, 1), date(2027, 1, 1), b)
        expected += 50.0 * 0.04 * yearfrac(date(2026, 10, 1), date(2027, 1, 1), b)

        out = run_nii_12m_base(positions, curve_set)
        self.assertAlmostEqual(out, expected, places=12)

    def test_run_nii_12m_base_excludes_non_maturity_types(self) -> None:
        """fixed_non_maturity is silently excluded (returns 0 NII)."""
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(analysis_date)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "X1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2028, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.05,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_non_maturity",
                }
            ]
        )

        out = run_nii_12m_base(positions, curve_set)
        self.assertAlmostEqual(out, 0.0, places=12)

    def test_run_nii_12m_scenarios_keeps_contract(self) -> None:
        analysis_date = date(2026, 1, 1)
        base_curve = _curve_set_for_analysis_date(analysis_date)
        up_curve = _curve_set_for_analysis_date(analysis_date)
        down_curve = _curve_set_for_analysis_date(analysis_date)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "A1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2028, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.05,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_bullet",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=base_curve,
            scenario_curve_sets={"parallel-up": up_curve, "parallel-down": down_curve},
        )

        self.assertEqual(out.analysis_date, analysis_date)
        self.assertIn("parallel-up", out.scenario_nii_12m)
        self.assertIn("parallel-down", out.scenario_nii_12m)
        self.assertAlmostEqual(out.base_nii_12m, out.scenario_nii_12m["parallel-up"], places=12)
        self.assertAlmostEqual(
            out.base_nii_12m,
            out.scenario_nii_12m["parallel-down"],
            places=12,
        )

    def test_fixed_bullet_rollover_is_scenario_sensitive(self) -> None:
        analysis_date = date(2026, 1, 1)

        def _curve(r: float) -> ForwardCurveSet:
            points = pd.DataFrame(
                [
                    {
                        "IndexName": "EUR_ESTR_OIS",
                        "Tenor": "1Y",
                        "FwdRate": r,
                        "TenorDate": date(2027, 1, 1),
                        "YearFrac": 1.0,
                    }
                ]
            )
            return ForwardCurveSet(
                analysis_date=analysis_date,
                base="ACT/365",
                points=points,
                curves={"EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS")},
            )

        base_curve = _curve(0.02)
        up_curve = _curve(0.04)
        down_curve = _curve(0.00)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "RB1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2026, 4, 1),  # vence dentro de 12m
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.05,
                    "daycount_base": "ACT/360",
                    "source_contract_type": "fixed_bullet",
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
