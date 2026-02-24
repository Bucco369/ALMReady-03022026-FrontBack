from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.services.eve import run_eve_scenarios
from engine.services.eve_analytics import (
    build_eve_bucket_breakdown_exact,
    build_eve_scenario_summary,
    worst_scenario_from_summary,
)
from engine.services.market import ForwardCurveSet


def _curve_set_for_analysis_date(analysis_date: date, *, rf_rate: float) -> ForwardCurveSet:
    points = pd.DataFrame(
        [
            {
                "IndexName": "EUR_ESTR_OIS",
                "Tenor": "1Y",
                "FwdRate": rf_rate,
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


class TestEVEAnalytics(unittest.TestCase):
    def test_summary_and_bucket_breakdown_match_exact_values(self) -> None:
        analysis_date = date(2026, 1, 1)
        base_curve = _curve_set_for_analysis_date(analysis_date, rf_rate=0.02)
        up_curve = _curve_set_for_analysis_date(analysis_date, rf_rate=0.04)
        down_curve = _curve_set_for_analysis_date(analysis_date, rf_rate=0.00)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "A1",
                    "start_date": date(2026, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "fixed",
                    "fixed_rate": 0.05,
                    "daycount_base": "ACT/365",
                    "source_contract_type": "fixed_bullet",
                }
            ]
        )

        run_out = run_eve_scenarios(
            positions=positions,
            base_discount_curve_set=base_curve,
            scenario_discount_curve_sets={"parallel-up": up_curve, "parallel-down": down_curve},
            method="exact",
        )
        summary = build_eve_scenario_summary(
            base_eve=run_out.base_eve,
            scenario_eve=run_out.scenario_eve,
        )
        worst = worst_scenario_from_summary(summary)
        self.assertEqual(worst, "parallel-up")

        buckets = [{"name": "0-2Y", "start_years": 0.0, "end_years": 2.0}]
        breakdown = build_eve_bucket_breakdown_exact(
            positions,
            base_discount_curve_set=base_curve,
            scenario_discount_curve_sets={"parallel-up": up_curve, "parallel-down": down_curve},
            buckets=buckets,
        )
        net = breakdown.loc[breakdown["side_group"] == "net"].copy()
        net_sum = (
            net.groupby("scenario", as_index=False)["pv_total"]
            .sum()
            .set_index("scenario")["pv_total"]
            .to_dict()
        )
        self.assertAlmostEqual(float(net_sum["base"]), float(run_out.base_eve), places=10)
        self.assertAlmostEqual(
            float(net_sum["parallel-up"]),
            float(run_out.scenario_eve["parallel-up"]),
            places=10,
        )
        self.assertAlmostEqual(
            float(net_sum["parallel-down"]),
            float(run_out.scenario_eve["parallel-down"]),
            places=10,
        )


if __name__ == "__main__":
    unittest.main()

