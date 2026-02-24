from __future__ import annotations

"""
Pipeline de EVE para ejecucion de extremo a extremo.

Este modulo conecta:
1) carga de posiciones/fujos,
2) construccion de curvas base y estresadas,
3) calculo EVE,
4) analytics por bucket,
5) generacion de graficos y export de tablas.

Objetivo: ofrecer un punto unico para ejecutar EVE con configuracion declarativa
sin tocar logica de bajo nivel.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from almready.io._utils import mapping_attr as _mapping_attr
from almready.io.positions_pipeline import load_positions_from_specs
from almready.io.scheduled_reader import load_scheduled_from_specs
from almready.services.eve_analytics import (
    build_eve_bucket_breakdown_exact,
    build_eve_scenario_summary,
    worst_scenario_from_summary,
)
from almready.services.eve_charts import (
    plot_eve_base_vs_worst_by_bucket,
    plot_eve_scenario_deltas,
    plot_eve_worst_delta_by_bucket,
)
from almready.services.eve import EVEBucket, EVERunResult, run_eve_scenarios
from almready.services.market import load_forward_curve_set
from almready.services.regulatory_curves import build_regulatory_curve_sets


@dataclass
class EVEPipelineResult:
    """Resultado completo de una corrida EVE de pipeline."""

    analysis_date: date
    method: str
    base_eve: float
    scenario_eve: dict[str, float]
    scenario_summary: pd.DataFrame
    worst_scenario: str | None
    bucket_breakdown: pd.DataFrame
    chart_paths: dict[str, Path]
    table_paths: dict[str, Path]
    positions_count: int
    scheduled_flows_count: int
    excluded_source_contract_types: dict[str, int]


_SUPPORTED_SOURCE_CONTRACT_TYPES = {
    "fixed_annuity",
    "fixed_bullet",
    "fixed_linear",
    "fixed_scheduled",
    "variable_annuity",
    "variable_bullet",
    "variable_linear",
    "variable_scheduled",
}
_EXCLUDED_SOURCE_CONTRACT_TYPES = {"static_position"}


def _scheduled_specs_from_source_specs(
    source_specs: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for spec in source_specs:
        sct = str(spec.get("source_contract_type", "")).strip().lower()
        name = str(spec.get("name", "")).strip().lower()
        pattern = str(spec.get("pattern", "")).strip().lower()
        if "scheduled" in sct or "scheduled" in name or "scheduled" in pattern:
            out.append(spec)
    return out


def load_positions_and_scheduled_flows(
    *,
    positions_root_path: str | Path,
    mapping_module: Any,
    source_specs: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga posiciones canonicas y flujos scheduled (principal) desde SOURCE_SPECS.

    - positions: todas las fuentes tabulares definidas en mapping.
    - flows: solo las fuentes detectadas como scheduled.
    """
    specs = (
        list(source_specs)
        if source_specs is not None
        else list(_mapping_attr(mapping_module, "SOURCE_SPECS"))
    )
    if not specs:
        raise ValueError("SOURCE_SPECS vacio: define al menos una fuente.")

    positions = load_positions_from_specs(
        root_path=positions_root_path,
        mapping_module=mapping_module,
        source_specs=specs,
    )

    scheduled_specs = _scheduled_specs_from_source_specs(specs)
    if not scheduled_specs:
        empty = pd.DataFrame(columns=["contract_id", "flow_date", "principal_amount"])
        return positions, empty

    scheduled_result = load_scheduled_from_specs(
        root_path=positions_root_path,
        mapping_module=mapping_module,
        source_specs=scheduled_specs,
    )
    flows = scheduled_result.principal_flows.copy()
    return positions, flows


def run_eve_from_specs(
    *,
    positions_root_path: str | Path,
    mapping_module: Any,
    curves_path: str | Path,
    analysis_date: date,
    curve_base: str = "ACT/360",
    curve_sheet: int | str = 0,
    risk_free_index: str = "EUR_ESTR_OIS",
    currency: str = "EUR",
    scenario_ids: Sequence[str] = ("parallel-up", "parallel-down"),
    method: str = "exact",
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
    open_ended_bucket_years: float = 10.0,
    preserve_basis_for_non_risk_free: bool = True,
    apply_post_shock_floor: bool = True,
    source_specs: Sequence[Mapping[str, Any]] | None = None,
    analytics_buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
    build_charts: bool = True,
    charts_output_dir: str | Path | None = None,
    export_tables: bool = True,
) -> EVEPipelineResult:
    """
    Ejecuta EVE completo desde ficheros de entrada declarados por mapping.

    Flujo:
    1) carga posiciones/flujos,
    2) filtra tipos no soportados en fase actual,
    3) construye curvas base + escenarios regulatorios,
    4) calcula EVE (exact o bucketed),
    5) calcula resumen y breakdown exacto por bucket,
    6) opcionalmente exporta tablas y grafica.
    """
    positions, scheduled_flows = load_positions_and_scheduled_flows(
        positions_root_path=positions_root_path,
        mapping_module=mapping_module,
        source_specs=source_specs,
    )
    excluded_types: dict[str, int] = {}
    if "source_contract_type" in positions.columns:
        sct = positions["source_contract_type"].astype("string").fillna("").str.strip().str.lower()
        counts = sct[sct != ""].value_counts()
        keep_mask = sct.isin(_SUPPORTED_SOURCE_CONTRACT_TYPES)
        ignore_mask = sct.isin(_EXCLUDED_SOURCE_CONTRACT_TYPES) | sct.eq("")
        drop_mask = (~keep_mask) & (~ignore_mask)
        if bool(drop_mask.any()):
            for key, val in counts.to_dict().items():
                if key in _SUPPORTED_SOURCE_CONTRACT_TYPES or key in _EXCLUDED_SOURCE_CONTRACT_TYPES:
                    continue
                excluded_types[str(key)] = int(val)
            positions = positions.loc[keep_mask | ignore_mask].copy()

    base_curve_set = load_forward_curve_set(
        path=str(Path(curves_path)),
        analysis_date=analysis_date,
        base=curve_base,
        sheet_name=curve_sheet,
    )

    scenario_curve_sets = build_regulatory_curve_sets(
        base_curve_set,
        scenarios=tuple(str(s).strip().lower() for s in scenario_ids),
        risk_free_index=risk_free_index,
        currency=currency,
        apply_post_shock_floor=apply_post_shock_floor,
        preserve_basis_for_non_risk_free=preserve_basis_for_non_risk_free,
    )

    out: EVERunResult = run_eve_scenarios(
        positions=positions,
        base_discount_curve_set=base_curve_set,
        scenario_discount_curve_sets=scenario_curve_sets,
        base_projection_curve_set=base_curve_set,
        scenario_projection_curve_sets=scenario_curve_sets,
        scheduled_principal_flows=scheduled_flows,
        discount_index=risk_free_index,
        method=method,
        buckets=buckets,
        open_ended_bucket_years=open_ended_bucket_years,
    )

    scenario_summary = build_eve_scenario_summary(
        base_eve=float(out.base_eve),
        scenario_eve={k: float(v) for k, v in out.scenario_eve.items()},
    )
    worst_scenario = worst_scenario_from_summary(scenario_summary)
    bucket_breakdown = build_eve_bucket_breakdown_exact(
        positions=positions,
        base_discount_curve_set=base_curve_set,
        scenario_discount_curve_sets=scenario_curve_sets,
        base_projection_curve_set=base_curve_set,
        scenario_projection_curve_sets=scenario_curve_sets,
        scheduled_principal_flows=scheduled_flows,
        discount_index=risk_free_index,
        buckets=analytics_buckets,
    )

    out_dir = Path(charts_output_dir) if charts_output_dir is not None else (
        Path.cwd() / "almready" / "tests" / "out"
    )
    chart_paths: dict[str, Path] = {}
    table_paths: dict[str, Path] = {}
    if build_charts:
        chart_paths["eve_scenario_deltas"] = plot_eve_scenario_deltas(
            scenario_summary,
            output_path=out_dir / "eve_scenario_deltas.png",
            title="EVE: delta vs base por escenario",
        )
        if worst_scenario is not None:
            chart_paths["eve_base_vs_worst_by_bucket"] = plot_eve_base_vs_worst_by_bucket(
                bucket_breakdown,
                scenario_summary=scenario_summary,
                output_path=out_dir / "eve_base_vs_worst_by_bucket.png",
                title=f"EVE por bucket: Base vs {worst_scenario}",
            )
            chart_paths["eve_worst_delta_by_bucket"] = plot_eve_worst_delta_by_bucket(
                bucket_breakdown,
                scenario_summary=scenario_summary,
                output_path=out_dir / "eve_worst_delta_by_bucket.png",
                title=f"{worst_scenario}: delta por bucket (neto/acumulado)",
            )
    if export_tables:
        out_dir.mkdir(parents=True, exist_ok=True)
        scenario_summary_path = out_dir / "eve_scenario_summary.csv"
        bucket_breakdown_path = out_dir / "eve_bucket_breakdown.csv"
        scenario_summary.to_csv(scenario_summary_path, index=False)
        bucket_breakdown.to_csv(bucket_breakdown_path, index=False)
        table_paths["eve_scenario_summary"] = scenario_summary_path
        table_paths["eve_bucket_breakdown"] = bucket_breakdown_path

    return EVEPipelineResult(
        analysis_date=analysis_date,
        method=out.method,
        base_eve=float(out.base_eve),
        scenario_eve={k: float(v) for k, v in out.scenario_eve.items()},
        scenario_summary=scenario_summary,
        worst_scenario=worst_scenario,
        bucket_breakdown=bucket_breakdown,
        chart_paths=chart_paths,
        table_paths=table_paths,
        positions_count=int(len(positions)),
        scheduled_flows_count=int(len(scheduled_flows)),
        excluded_source_contract_types=excluded_types,
    )
