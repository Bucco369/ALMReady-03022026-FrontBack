from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from engine.core.curves import curve_from_long_df
from engine.scenarios.regulatory import (
    apply_regulatory_shock_rate,
    maturity_post_shock_floor,
    shock_parameters_for_currency,
)
from engine.services.market import ForwardCurveSet
from engine.services.regulatory_curves import build_regulatory_curve_set


def _base_curve_set() -> ForwardCurveSet:
    analysis_date = date(2025, 12, 31)
    points = pd.DataFrame(
        [
            {
                "IndexName": "EUR_ESTR_OIS",
                "Tenor": "1Y",
                "FwdRate": 0.0200,
                "TenorDate": date(2026, 12, 31),
                "YearFrac": 1.0,
            },
            {
                "IndexName": "EUR_ESTR_OIS",
                "Tenor": "5Y",
                "FwdRate": 0.0250,
                "TenorDate": date(2030, 12, 31),
                "YearFrac": 5.0,
            },
            {
                "IndexName": "EUR_EURIBOR_3M",
                "Tenor": "1Y",
                "FwdRate": 0.0300,
                "TenorDate": date(2026, 12, 31),
                "YearFrac": 1.0,
            },
            {
                "IndexName": "EUR_EURIBOR_3M",
                "Tenor": "5Y",
                "FwdRate": 0.0350,
                "TenorDate": date(2030, 12, 31),
                "YearFrac": 5.0,
            },
        ]
    )

    curves = {}
    for ix in sorted(points["IndexName"].unique().tolist()):
        curves[ix] = curve_from_long_df(points, ix)

    return ForwardCurveSet(
        analysis_date=analysis_date,
        base="ACT/365",
        points=points,
        curves=curves,
    )


class TestRegulatoryCurves(unittest.TestCase):
    def test_shock_parameters_for_eur_match_annex(self) -> None:
        p = shock_parameters_for_currency("EUR")
        self.assertAlmostEqual(p.parallel, 0.0200, places=12)
        self.assertAlmostEqual(p.short, 0.0250, places=12)
        self.assertAlmostEqual(p.long, 0.0100, places=12)

    def test_maturity_floor_profile(self) -> None:
        self.assertAlmostEqual(maturity_post_shock_floor(0.0), -0.0150, places=12)
        self.assertAlmostEqual(maturity_post_shock_floor(10.0), -0.0120, places=12)
        self.assertAlmostEqual(maturity_post_shock_floor(50.0), 0.0, places=12)
        self.assertAlmostEqual(maturity_post_shock_floor(80.0), 0.0, places=12)

    def test_apply_regulatory_floor_with_observed_lower_rule(self) -> None:
        p = shock_parameters_for_currency("EUR")

        # Caso con observed lower rate por debajo del floor: se respeta el observado.
        shocked_low = apply_regulatory_shock_rate(
            base_rate=-0.02,
            t_years=2.0,
            scenario_id="parallel-down",
            shock_parameters=p,
            apply_post_shock_floor=True,
        )
        self.assertAlmostEqual(shocked_low, -0.02, places=12)

        # Caso sin observed lower: aplica floor por plazo.
        shocked_floor = apply_regulatory_shock_rate(
            base_rate=0.0,
            t_years=0.0,
            scenario_id="parallel-down",
            shock_parameters=p,
            apply_post_shock_floor=True,
        )
        self.assertAlmostEqual(shocked_floor, -0.015, places=12)

    def test_build_regulatory_curve_set_preserves_basis(self) -> None:
        base = _base_curve_set()
        stressed = build_regulatory_curve_set(
            base,
            scenario_id="parallel-up",
            risk_free_index="EUR_ESTR_OIS",
            currency="EUR",
            apply_post_shock_floor=True,
            preserve_basis_for_non_risk_free=True,
        )

        # En los pilares, spread EURIBOR3M - ESTR se preserva.
        for t in (1.0, 5.0):
            spread_base = base.get("EUR_EURIBOR_3M").rate(t) - base.get("EUR_ESTR_OIS").rate(t)
            spread_stressed = (
                stressed.get("EUR_EURIBOR_3M").rate(t) - stressed.get("EUR_ESTR_OIS").rate(t)
            )
            self.assertAlmostEqual(spread_stressed, spread_base, places=12)

        # Parallel up en EUR: +200 bps en la risk-free.
        self.assertAlmostEqual(stressed.get("EUR_ESTR_OIS").rate(1.0), 0.04, places=12)


if __name__ == "__main__":
    unittest.main()
