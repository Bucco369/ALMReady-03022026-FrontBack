from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from almready.core.curves import ForwardCurve, curve_from_long_df
from almready.scenarios.regulatory import (
    DEFAULT_FLOOR_PARAMETERS,
    PostShockFloorParameters,
    RegulatoryShockParameters,
    apply_regulatory_shock_rate,
    shock_parameters_for_currency,
)
from almready.services.market import ForwardCurveSet


@dataclass(frozen=True)
class RegulatoryScenarioSpec:
    scenario_id: str
    name: str


def _validate_curve_points_columns(df_points: pd.DataFrame) -> None:
    required = ["IndexName", "Tenor", "FwdRate", "TenorDate", "YearFrac"]
    missing = [c for c in required if c not in df_points.columns]
    if missing:
        raise ValueError(
            "ForwardCurveSet.points no contiene columnas requeridas: "
            f"{missing}"
        )


def _rebuild_curves(df_points: pd.DataFrame) -> dict[str, ForwardCurve]:
    indexes = sorted(df_points["IndexName"].astype(str).unique().tolist())
    curves: dict[str, ForwardCurve] = {}
    for index_name in indexes:
        curves[index_name] = curve_from_long_df(df_points, index_name=index_name)
    return curves


def _normalise_specs(
    specs: Iterable[str | RegulatoryScenarioSpec],
) -> list[RegulatoryScenarioSpec]:
    out: list[RegulatoryScenarioSpec] = []
    names_seen: set[str] = set()
    for raw in specs:
        if isinstance(raw, RegulatoryScenarioSpec):
            spec = raw
        else:
            sid = str(raw).strip().lower()
            spec = RegulatoryScenarioSpec(scenario_id=sid, name=sid)

        if spec.name in names_seen:
            raise ValueError(f"Nombre de escenario duplicado: {spec.name!r}")
        names_seen.add(spec.name)
        out.append(spec)

    if not out:
        raise ValueError("Se requiere al menos un escenario.")
    return out


def build_regulatory_curve_set(
    base_set: ForwardCurveSet,
    *,
    scenario_id: str,
    risk_free_index: str,
    currency: str = "EUR",
    shock_parameters: RegulatoryShockParameters | None = None,
    floor_parameters: PostShockFloorParameters = DEFAULT_FLOOR_PARAMETERS,
    apply_post_shock_floor: bool = True,
    preserve_basis_for_non_risk_free: bool = True,
) -> ForwardCurveSet:
    """
    Genera un ForwardCurveSet estresado para un escenario regulatorio.

    Regla para indices no risk-free (si preserve_basis_for_non_risk_free=True):
      idx_stressed(t) = rf_stressed(t) + (idx_base(t) - rf_base(t))
    """
    _validate_curve_points_columns(base_set.points)
    risk_free_index = str(risk_free_index).strip()
    base_set.require_indices([risk_free_index])

    params = shock_parameters or shock_parameters_for_currency(currency)
    base_rf_curve = base_set.get(risk_free_index)
    base_curves = base_set.curves

    df_shifted = base_set.points.copy(deep=True)

    def _stressed_rate(index_name: str, t_years: float) -> float:
        rf_base = base_rf_curve.rate(t_years)
        rf_stressed = apply_regulatory_shock_rate(
            base_rate=rf_base,
            t_years=t_years,
            scenario_id=scenario_id,
            shock_parameters=params,
            apply_post_shock_floor=apply_post_shock_floor,
            floor_parameters=floor_parameters,
        )
        if (not preserve_basis_for_non_risk_free) or index_name == risk_free_index:
            return rf_stressed

        idx_base = base_curves[index_name].rate(t_years)
        basis = idx_base - rf_base
        return rf_stressed + basis

    rates_out: list[float] = []
    for row in df_shifted.itertuples(index=False):
        index_name = str(row.IndexName)
        t_years = float(row.YearFrac)
        rates_out.append(_stressed_rate(index_name, t_years))

    df_shifted["FwdRate"] = rates_out
    shifted_curves = _rebuild_curves(df_shifted)

    return ForwardCurveSet(
        analysis_date=base_set.analysis_date,
        base=base_set.base,
        points=df_shifted,
        curves=shifted_curves,
    )


def build_regulatory_curve_sets(
    base_set: ForwardCurveSet,
    *,
    scenarios: Iterable[str | RegulatoryScenarioSpec],
    risk_free_index: str,
    currency: str = "EUR",
    shock_parameters: RegulatoryShockParameters | None = None,
    floor_parameters: PostShockFloorParameters = DEFAULT_FLOOR_PARAMETERS,
    apply_post_shock_floor: bool = True,
    preserve_basis_for_non_risk_free: bool = True,
) -> dict[str, ForwardCurveSet]:
    """
    Ejecuta varios escenarios y devuelve name -> ForwardCurveSet.
    """
    specs = _normalise_specs(scenarios)
    out: dict[str, ForwardCurveSet] = {}
    for spec in specs:
        out[spec.name] = build_regulatory_curve_set(
            base_set=base_set,
            scenario_id=spec.scenario_id,
            risk_free_index=risk_free_index,
            currency=currency,
            shock_parameters=shock_parameters,
            floor_parameters=floor_parameters,
            apply_post_shock_floor=apply_post_shock_floor,
            preserve_basis_for_non_risk_free=preserve_basis_for_non_risk_free,
        )
    return out
