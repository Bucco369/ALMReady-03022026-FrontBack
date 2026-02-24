from __future__ import annotations

from datetime import date
import unittest

import pandas as pd
from dateutil.relativedelta import relativedelta

from engine.core.curves import curve_from_long_df
from engine.core.daycount import normalize_daycount_base, yearfrac
from engine.services.market import ForwardCurveSet
from engine.services.nii import run_nii_12m_scenarios


def _one_index_curve_set(
    *,
    analysis_date: date,
    index_name: str,
    rate_1y: float,
) -> ForwardCurveSet:
    point = pd.DataFrame(
        [
            {
                "IndexName": index_name,
                "Tenor": "1Y",
                "FwdRate": float(rate_1y),
                "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
                "YearFrac": 1.0,
            }
        ]
    )
    curves = {index_name: curve_from_long_df(point, index_name)}
    return ForwardCurveSet(
        analysis_date=analysis_date,
        base="ACT/360",
        points=point,
        curves=curves,
    )


def _sloped_curve_set(
    *,
    analysis_date: date,
    index_name: str,
) -> ForwardCurveSet:
    point = pd.DataFrame(
        [
            {
                "IndexName": index_name,
                "Tenor": "6M",
                "FwdRate": 0.01,
                "TenorDate": analysis_date + relativedelta(months=6),
                "YearFrac": 0.5,
            },
            {
                "IndexName": index_name,
                "Tenor": "2Y",
                "FwdRate": 0.04,
                "TenorDate": date(analysis_date.year + 2, analysis_date.month, analysis_date.day),
                "YearFrac": 2.0,
            },
        ]
    )
    curves = {index_name: curve_from_long_df(point, index_name)}
    return ForwardCurveSet(
        analysis_date=analysis_date,
        base="ACT/360",
        points=point,
        curves=curves,
    )


class TestNIIVariableAnnuity(unittest.TestCase):
    def test_variable_annuity_is_scenario_sensitive(self) -> None:
        analysis_date = date(2026, 1, 1)
        index_name = "EURIBOR_SWAP"

        base_curve = _one_index_curve_set(analysis_date=analysis_date, index_name=index_name, rate_1y=0.02)
        up_curve = _one_index_curve_set(analysis_date=analysis_date, index_name=index_name, rate_1y=0.04)
        down_curve = _one_index_curve_set(analysis_date=analysis_date, index_name=index_name, rate_1y=0.00)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "VA1",
                    "start_date": date(2026, 1, 1),
                    "maturity_date": date(2028, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "float",
                    "daycount_base": "ACT/360",
                    "index_name": index_name,
                    "spread": 0.01,
                    "fixed_rate": None,
                    "repricing_freq": "12M",
                    "next_reprice_date": date(2026, 1, 1),
                    "payment_freq": "12M",
                    "floor_rate": None,
                    "cap_rate": None,
                    "source_contract_type": "variable_annuity",
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

    def test_variable_annuity_uses_fixed_rate_until_first_future_reset(self) -> None:
        analysis_date = date(2026, 1, 1)
        index_name = "EURIBOR_SWAP"
        curve_set = _one_index_curve_set(analysis_date=analysis_date, index_name=index_name, rate_1y=0.02)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "VA2",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "float",
                    "daycount_base": "ACT/360",
                    "index_name": index_name,
                    "spread": 0.01,
                    "fixed_rate": 0.06,
                    "repricing_freq": "6M",
                    "next_reprice_date": date(2026, 4, 1),
                    "payment_freq": "12M",
                    "floor_rate": None,
                    "cap_rate": None,
                    "source_contract_type": "variable_annuity",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
        )

        b = normalize_daycount_base("ACT/360")
        yf_stub = yearfrac(date(2026, 1, 1), date(2026, 4, 1), b)
        yf_rest = yearfrac(date(2026, 4, 1), date(2027, 1, 1), b)
        expected = 100.0 * 0.06 * yf_stub + 100.0 * (0.02 + 0.01) * yf_rest
        self.assertAlmostEqual(out.base_nii_12m, expected, places=10)

    def test_variable_annuity_payment_mode_is_configurable(self) -> None:
        analysis_date = date(2026, 1, 1)
        index_name = "EURIBOR_SWAP"
        curve_set = _sloped_curve_set(analysis_date=analysis_date, index_name=index_name)

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "VA3",
                    "start_date": date(2026, 1, 1),
                    "maturity_date": date(2028, 1, 1),
                    "notional": 1000.0,
                    "side": "A",
                    "rate_type": "float",
                    "daycount_base": "ACT/360",
                    "index_name": index_name,
                    "spread": 0.0,
                    "fixed_rate": None,
                    "repricing_freq": "3M",
                    "next_reprice_date": date(2026, 1, 1),
                    "payment_freq": "6M",
                    "floor_rate": None,
                    "cap_rate": None,
                    "source_contract_type": "variable_annuity",
                }
            ]
        )

        out_default = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
        )
        out_reprice = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
            variable_annuity_payment_mode="reprice_on_reset",
        )
        out_fixed = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=curve_set,
            scenario_curve_sets={},
            variable_annuity_payment_mode="fixed_payment",
        )

        self.assertAlmostEqual(out_default.base_nii_12m, out_reprice.base_nii_12m, places=12)
        self.assertNotAlmostEqual(out_reprice.base_nii_12m, out_fixed.base_nii_12m, places=8)


if __name__ == "__main__":
    unittest.main()
