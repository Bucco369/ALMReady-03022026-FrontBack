from __future__ import annotations

from datetime import date
from math import exp, log
import unittest

from engine.core.curves import CurvePoint, ForwardCurve


def _sample_curve() -> ForwardCurve:
    return ForwardCurve(
        index_name="TEST_INDEX",
        points=[
            CurvePoint(
                year_frac=1.0,
                rate=0.02,
                tenor="1Y",
                tenor_date=date(2026, 1, 1),
            ),
            CurvePoint(
                year_frac=2.0,
                rate=0.03,
                tenor="2Y",
                tenor_date=date(2027, 1, 1),
            ),
        ],
    )


class TestCurveInterpolation(unittest.TestCase):
    def test_discount_factor_is_exact_on_pillars(self) -> None:
        curve = _sample_curve()

        self.assertAlmostEqual(curve.discount_factor(1.0), exp(-0.02), places=12)
        self.assertAlmostEqual(curve.discount_factor(2.0), exp(-0.06), places=12)

    def test_discount_factor_interpolates_log_linearly_between_pillars(self) -> None:
        curve = _sample_curve()

        # Midpoint in ln(DF): lnDF(1.5) = -0.04
        expected_df = exp(-0.04)
        self.assertAlmostEqual(curve.discount_factor(1.5), expected_df, places=12)

    def test_discount_factor_interpolates_from_origin_to_first_pillar(self) -> None:
        curve = _sample_curve()

        # Between (0, lnDF=0) and (1, lnDF=-0.02): lnDF(0.5) = -0.01
        expected_df = exp(-0.01)
        self.assertAlmostEqual(curve.discount_factor(0.5), expected_df, places=12)

    def test_discount_factor_extrapolates_with_last_segment_slope(self) -> None:
        curve = _sample_curve()

        # Last-segment slope in lnDF: (-0.06 - -0.02) / (2 - 1) = -0.04
        # lnDF(3.0) = -0.06 + (3-2)*(-0.04) = -0.10
        expected_df = exp(-0.10)
        self.assertAlmostEqual(curve.discount_factor(3.0), expected_df, places=12)

    def test_zero_rate_matches_discount_factor_identity(self) -> None:
        curve = _sample_curve()
        t = 1.75
        df = curve.discount_factor(t)
        expected = -log(df) / t
        self.assertAlmostEqual(curve.zero_rate(t), expected, places=12)

    def test_single_pillar_curve_behaves_consistently(self) -> None:
        curve = ForwardCurve(
            index_name="ONE_PILLAR",
            points=[
                CurvePoint(
                    year_frac=1.0,
                    rate=0.03,
                    tenor="1Y",
                    tenor_date=date(2026, 1, 1),
                )
            ],
        )

        self.assertAlmostEqual(curve.discount_factor(0.5), exp(-0.015), places=12)
        self.assertAlmostEqual(curve.discount_factor(2.0), exp(-0.06), places=12)


if __name__ == "__main__":
    unittest.main()
