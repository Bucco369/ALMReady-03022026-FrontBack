from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from engine.services.market import ForwardCurveSet, load_forward_curve_set


def _sample_curves_wide() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "IndexName": "EUR_EURIBOR_3M",
                "ON": "2.85%",
                "1M": "2.95%",
                "3M": 0.0310,
            },
            {
                "IndexName": "EUR_ESTR_OIS",
                "ON": "2.75%",
                "1M": "2.80%",
                "3M": "2.90%",
            },
        ]
    )


def _build_curve_set() -> ForwardCurveSet:
    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "curves_sample.xlsx"
        _sample_curves_wide().to_excel(path, index=False)
        curve_set = load_forward_curve_set(
            path=str(path),
            analysis_date=date(2025, 12, 31),
            base="ACT/360",
            sheet_name=0,
        )
    return curve_set


class TestMarketLoader(unittest.TestCase):
    def test_load_forward_curve_set_from_excel(self) -> None:
        curve_set = _build_curve_set()

        self.assertEqual(curve_set.analysis_date, date(2025, 12, 31))
        self.assertEqual(curve_set.base, "ACT/360")
        self.assertEqual(len(curve_set.curves), 2)
        self.assertEqual(len(curve_set.points), 6)

        expected_columns = {"IndexName", "Tenor", "FwdRate", "TenorDate", "YearFrac"}
        self.assertEqual(set(curve_set.points.columns), expected_columns)

    def test_rate_and_df_queries_return_values(self) -> None:
        curve_set = _build_curve_set()

        rate = curve_set.rate_on_date("EUR_EURIBOR_3M", date(2026, 3, 31))
        df = curve_set.df_on_date("EUR_EURIBOR_3M", date(2026, 3, 31))

        self.assertIsInstance(rate, float)
        self.assertIsInstance(df, float)
        self.assertGreater(df, 0.0)
        self.assertLess(df, 1.0)

    def test_unknown_index_raises_key_error(self) -> None:
        curve_set = _build_curve_set()
        with self.assertRaises(KeyError):
            curve_set.get("MISSING_INDEX")

    def test_df_extrapolation_after_last_pillar_keeps_discounting(self) -> None:
        curve_set = _build_curve_set()

        ix = "EUR_EURIBOR_3M"
        df_3m = curve_set.df_on_date(ix, date(2026, 3, 31))
        df_far = curve_set.df_on_date(ix, date(2028, 12, 31))

        self.assertGreater(df_3m, 0.0)
        self.assertGreater(df_far, 0.0)
        self.assertLess(df_far, df_3m)

    def test_df_is_continuous_between_origin_and_first_pillar(self) -> None:
        curve_set = _build_curve_set()
        curve = curve_set.get("EUR_EURIBOR_3M")

        t_first = curve.year_fracs[0]
        df_first = curve.discount_factor(t_first)
        df_half = curve.discount_factor(t_first * 0.5)

        self.assertLess(df_half, 1.0)
        self.assertGreater(df_half, df_first)

    def test_require_indices_raises_when_missing(self) -> None:
        curve_set = _build_curve_set()

        curve_set.require_indices(["EUR_EURIBOR_3M", "EUR_ESTR_OIS"])
        with self.assertRaises(KeyError):
            curve_set.require_indices(["EUR_EURIBOR_3M", "EUR_EURIBOR_12M"])

    def test_require_float_index_coverage_validates_positions(self) -> None:
        curve_set = _build_curve_set()

        ok_positions = pd.DataFrame(
            [
                {"rate_type": "float", "index_name": "EUR_EURIBOR_3M"},
                {"rate_type": "fixed", "index_name": pd.NA},
            ]
        )
        curve_set.require_float_index_coverage(ok_positions)

        missing_index = pd.DataFrame(
            [
                {"rate_type": "float", "index_name": pd.NA},
            ]
        )
        with self.assertRaises(ValueError):
            curve_set.require_float_index_coverage(missing_index)

        missing_curve = pd.DataFrame(
            [
                {"rate_type": "float", "index_name": "EUR_EURIBOR_12M"},
            ]
        )
        with self.assertRaises(KeyError):
            curve_set.require_float_index_coverage(missing_curve)


if __name__ == "__main__":
    unittest.main()
