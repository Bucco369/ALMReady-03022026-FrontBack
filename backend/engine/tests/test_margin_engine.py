from __future__ import annotations

from datetime import date
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.services.margin_engine import (
    CalibratedMarginSet,
    calibrate_margin_set,
    load_margin_set_csv,
    save_margin_set_csv,
)
from engine.services.market import ForwardCurveSet


def _curve_set(analysis_date: date, rate_1y: float = 0.02) -> ForwardCurveSet:
    points = pd.DataFrame(
        [
            {
                "IndexName": "EUR_ESTR_OIS",
                "Tenor": "1Y",
                "FwdRate": rate_1y,
                "TenorDate": date(analysis_date.year + 1, analysis_date.month, analysis_date.day),
                "YearFrac": 1.0,
            }
        ]
    )
    curves = {"EUR_ESTR_OIS": curve_from_long_df(points, "EUR_ESTR_OIS")}
    return ForwardCurveSet(
        analysis_date=analysis_date,
        base="ACT/360",
        points=points,
        curves=curves,
    )


class TestMarginEngine(unittest.TestCase):
    def test_calibrate_and_lookup_margin_set(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve = _curve_set(analysis_date, rate_1y=0.02)

        recent = pd.DataFrame(
            [
                {
                    "rate_type": "fixed",
                    "source_contract_type": "fixed_bullet",
                    "side": "A",
                    "repricing_freq": "12M",
                    "index_name": pd.NA,
                    "fixed_rate": 0.05,
                    "notional": 100.0,
                },
                {
                    "rate_type": "float",
                    "source_contract_type": "variable_bullet",
                    "side": "A",
                    "repricing_freq": "3M",
                    "index_name": "EURIBOR_SWAP",
                    "spread": 0.012,
                    "notional": 200.0,
                },
            ]
        )

        margin_set = calibrate_margin_set(
            recent,
            curve_set=curve,
            risk_free_index="EUR_ESTR_OIS",
        )

        fixed_margin = margin_set.lookup_margin(
            rate_type="fixed",
            source_contract_type="fixed_bullet",
            side="A",
            repricing_freq="12M",
            default=0.0,
        )
        float_margin = margin_set.lookup_margin(
            rate_type="float",
            source_contract_type="variable_bullet",
            side="A",
            repricing_freq="3M",
            index_name="EURIBOR_SWAP",
            default=0.0,
        )

        self.assertAlmostEqual(fixed_margin, 0.03, places=10)
        self.assertAlmostEqual(float_margin, 0.012, places=10)

    def test_save_and_load_margin_set_csv(self) -> None:
        margin_set = CalibratedMarginSet(
            pd.DataFrame(
                [
                    {
                        "rate_type": "fixed",
                        "source_contract_type": "fixed_bullet",
                        "side": "A",
                        "repricing_freq": "12M",
                        "index_name": pd.NA,
                        "margin_rate": 0.025,
                        "weight": 100.0,
                    }
                ]
            )
        )

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "margins.csv"
            save_margin_set_csv(margin_set, p)
            loaded = load_margin_set_csv(p)

        out = loaded.lookup_margin(
            rate_type="fixed",
            source_contract_type="fixed_bullet",
            side="A",
            repricing_freq="12M",
            default=0.0,
        )
        self.assertAlmostEqual(out, 0.025, places=12)

    def test_calibrate_margin_set_applies_12m_lookback(self) -> None:
        analysis_date = date(2026, 1, 1)
        curve = _curve_set(analysis_date, rate_1y=0.02)

        rows = pd.DataFrame(
            [
                {
                    "start_date": date(2025, 7, 1),  # dentro de 12m
                    "rate_type": "fixed",
                    "source_contract_type": "fixed_bullet",
                    "side": "A",
                    "repricing_freq": "12M",
                    "fixed_rate": 0.05,
                    "notional": 100.0,
                },
                {
                    "start_date": date(2023, 7, 1),  # fuera de 12m
                    "rate_type": "fixed",
                    "source_contract_type": "fixed_bullet",
                    "side": "A",
                    "repricing_freq": "12M",
                    "fixed_rate": 0.20,
                    "notional": 100.0,
                },
            ]
        )

        ms = calibrate_margin_set(
            rows,
            curve_set=curve,
            as_of=analysis_date,
            lookback_months=12,
            start_date_col="start_date",
        )
        out = ms.lookup_margin(
            rate_type="fixed",
            source_contract_type="fixed_bullet",
            side="A",
            repricing_freq="12M",
            default=0.0,
        )
        # Solo cuenta la fila reciente: 0.05 - 0.02 = 0.03
        self.assertAlmostEqual(out, 0.03, places=12)


if __name__ == "__main__":
    unittest.main()
