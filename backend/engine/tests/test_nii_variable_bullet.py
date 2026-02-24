from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.core.daycount import normalizar_base_de_calculo, yearfrac
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


class TestNIIVariableBullet(unittest.TestCase):
    def test_variable_bullet_is_scenario_sensitive(self) -> None:
        analysis_date = date(2026, 1, 1)
        index_name = "EURIBOR_SWAP"

        base_curve = _one_index_curve_set(
            analysis_date=analysis_date,
            index_name=index_name,
            rate_1y=0.02,
        )
        up_curve = _one_index_curve_set(
            analysis_date=analysis_date,
            index_name=index_name,
            rate_1y=0.04,
        )
        down_curve = _one_index_curve_set(
            analysis_date=analysis_date,
            index_name=index_name,
            rate_1y=0.00,
        )

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "VB1",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2027, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "float",
                    "daycount_base": "ACT/360",
                    "index_name": index_name,
                    "spread": 0.01,
                    "fixed_rate": 0.05,
                    "repricing_freq": "6M",
                    "next_reprice_date": date(2025, 7, 1),
                    "floor_rate": None,
                    "cap_rate": None,
                    "source_contract_type": "variable_bullet",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=base_curve,
            scenario_curve_sets={"parallel-up": up_curve, "parallel-down": down_curve},
        )

        b = normalizar_base_de_calculo("ACT/360")
        yf = yearfrac(date(2026, 1, 1), date(2027, 1, 1), b)
        expected_base = 100.0 * (0.02 + 0.01) * yf
        expected_up = 100.0 * (0.04 + 0.01) * yf
        expected_down = 100.0 * (0.00 + 0.01) * yf

        self.assertAlmostEqual(out.base_nii_12m, expected_base, places=12)
        self.assertAlmostEqual(out.scenario_nii_12m["parallel-up"], expected_up, places=12)
        self.assertAlmostEqual(out.scenario_nii_12m["parallel-down"], expected_down, places=12)
        self.assertGreater(out.scenario_nii_12m["parallel-up"], out.base_nii_12m)
        self.assertLess(out.scenario_nii_12m["parallel-down"], out.base_nii_12m)

    def test_variable_bullet_uses_fixed_rate_until_first_future_reset(self) -> None:
        analysis_date = date(2026, 1, 1)
        index_name = "EURIBOR_SWAP"
        base_curve = _one_index_curve_set(
            analysis_date=analysis_date,
            index_name=index_name,
            rate_1y=0.02,
        )

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "VB2",
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
                    "floor_rate": None,
                    "cap_rate": None,
                    "source_contract_type": "variable_bullet",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=base_curve,
            scenario_curve_sets={},
        )

        b = normalizar_base_de_calculo("ACT/360")
        yf_stub = yearfrac(date(2026, 1, 1), date(2026, 4, 1), b)
        yf_rest = yearfrac(date(2026, 4, 1), date(2027, 1, 1), b)
        expected = 100.0 * 0.06 * yf_stub + 100.0 * (0.02 + 0.01) * yf_rest

        self.assertAlmostEqual(out.base_nii_12m, expected, places=12)

    def test_variable_bullet_keeps_fixed_rate_if_next_reset_is_beyond_horizon(self) -> None:
        analysis_date = date(2026, 1, 1)
        index_name = "EURIBOR_SWAP"
        base_curve = _one_index_curve_set(
            analysis_date=analysis_date,
            index_name=index_name,
            rate_1y=0.01,
        )

        positions = pd.DataFrame(
            [
                {
                    "contract_id": "VB3",
                    "start_date": date(2025, 1, 1),
                    "maturity_date": date(2028, 1, 1),
                    "notional": 100.0,
                    "side": "A",
                    "rate_type": "float",
                    "daycount_base": "ACT/360",
                    "index_name": index_name,
                    "spread": 0.00,
                    "fixed_rate": 0.05,
                    "repricing_freq": "12M",
                    "next_reprice_date": date(2027, 6, 1),
                    "floor_rate": None,
                    "cap_rate": None,
                    "source_contract_type": "variable_bullet",
                }
            ]
        )

        out = run_nii_12m_scenarios(
            positions=positions,
            base_curve_set=base_curve,
            scenario_curve_sets={},
        )

        b = normalizar_base_de_calculo("ACT/360")
        yf = yearfrac(date(2026, 1, 1), date(2027, 1, 1), b)
        expected = 100.0 * 0.05 * yf
        self.assertAlmostEqual(out.base_nii_12m, expected, places=12)


if __name__ == "__main__":
    unittest.main()
