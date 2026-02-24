from __future__ import annotations

from datetime import date
from math import exp
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.services.eve import (
    build_eve_cashflows,
    run_eve_base,
    run_eve_scenarios,
)
from engine.services.market import ForwardCurveSet


def _curve_set_for_analysis_date(
    analysis_date: date,
    *,
    rf_rate: float,
    euribor_3m_rate: float,
) -> ForwardCurveSet:
    points = pd.DataFrame(
        [
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
                "FwdRate": euribor_3m_rate,
                "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
                "YearFrac": 1.0,
            },
        ]
    )
    curves = {
        "EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS"),
        "EUR_EURIBOR_3M": curve_from_long_df(points, "EUR_EURIBOR_3M"),
    }
    return ForwardCurveSet(
        analysis_date=analysis_date,
        base="ACT/365",
        points=points,
        curves=curves,
    )


class TestEVEEngine(unittest.TestCase):
    def test_run_eve_exact_fixed_bullet(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(
            analysis_date,
            rf_rate=0.02,
            euribor_3m_rate=0.03,
        )
        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FB1",
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

        out = run_eve_base(
            positions,
            curve_set,
            projection_curve_set=curve_set,
            method="exact",
        )
        expected = 105.0 * exp(-0.02 * 1.0)
        self.assertAlmostEqual(out, expected, places=10)

    def test_variable_bullet_uses_full_rate_index_plus_spread(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(
            analysis_date,
            rf_rate=0.02,
            euribor_3m_rate=0.02,
        )
        positions = pd.DataFrame(
            [
                {
                    "contract_id": "VB1",
                    "start_date": date(2026, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "float",
                    "index_name": "EUR_EURIBOR_3M",
                    "spread": 0.01,
                    "daycount_base": "ACT/365",
                    "source_contract_type": "variable_bullet",
                }
            ]
        )

        cfs = build_eve_cashflows(
            positions,
            analysis_date=analysis_date,
            projection_curve_set=curve_set,
        )
        self.assertAlmostEqual(float(cfs["interest_amount"].sum()), 3.0, places=10)
        self.assertAlmostEqual(float(cfs["principal_amount"].sum()), 100.0, places=10)

        out = run_eve_base(
            positions,
            curve_set,
            projection_curve_set=curve_set,
            method="exact",
        )
        expected = 103.0 * exp(-0.02 * 1.0)
        self.assertAlmostEqual(out, expected, places=10)

    def test_bucketed_mode_with_custom_bucket(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve_set = _curve_set_for_analysis_date(
            analysis_date,
            rf_rate=0.02,
            euribor_3m_rate=0.03,
        )
        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FB2",
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

        exact = run_eve_base(
            positions,
            curve_set,
            projection_curve_set=curve_set,
            method="exact",
        )
        bucketed = run_eve_base(
            positions,
            curve_set,
            projection_curve_set=curve_set,
            method="bucketed",
            buckets=[{"name": "0-2Y", "start_years": 0.0, "end_years": 2.0}],
        )
        self.assertAlmostEqual(bucketed, exact, places=10)

    def test_run_eve_scenarios_parallel_order(self) -> None:
        analysis_date = date(2026, 1, 1)
        base_curve = _curve_set_for_analysis_date(
            analysis_date,
            rf_rate=0.02,
            euribor_3m_rate=0.03,
        )
        up_curve = _curve_set_for_analysis_date(
            analysis_date,
            rf_rate=0.04,
            euribor_3m_rate=0.05,
        )
        down_curve = _curve_set_for_analysis_date(
            analysis_date,
            rf_rate=0.00,
            euribor_3m_rate=0.01,
        )

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "FB3",
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

        out = run_eve_scenarios(
            positions,
            base_discount_curve_set=base_curve,
            scenario_discount_curve_sets={
                "parallel-up": up_curve,
                "parallel-down": down_curve,
            },
            method="exact",
        )
        self.assertGreater(out.scenario_eve["parallel-down"], out.base_eve)
        self.assertLess(out.scenario_eve["parallel-up"], out.base_eve)


if __name__ == "__main__":
    unittest.main()

