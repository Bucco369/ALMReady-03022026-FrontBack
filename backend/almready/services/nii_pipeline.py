from __future__ import annotations

"""
Pipeline de NII para ejecucion de extremo a extremo.

Este modulo conecta:
1) carga de posiciones/flows,
2) curvas base + escenarios,
3) calculo NII 12M,
4) perfil mensual para visualizacion,
5) grafico mensual base/up/down.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from almready.services.eve_pipeline import load_positions_and_scheduled_flows
from almready.services.market import load_forward_curve_set
from almready.config import NII_HORIZON_MONTHS
from almready.services.nii import (
    NIIMonthlyProfileResult,
    run_nii_12m_scenarios_with_monthly_profile,
)
from almready.services.nii_charts import (
    plot_nii_base_vs_worst_by_month,
    plot_nii_monthly_profile,
)
from almready.services.regulatory_curves import build_regulatory_curve_sets


@dataclass
class NIIPipelineResult:
    """Resultado agregado de la corrida NII de pipeline."""

    analysis_date: date
    base_nii_12m: float
    scenario_nii_12m: dict[str, float]
    monthly_profile: pd.DataFrame
    chart_path: Path | None
    chart_base_vs_worst_path: Path | None
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


def run_nii_from_specs(
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
    balance_constant: bool = True,
    margin_lookback_months: int | None = 12,
    margin_start_date_col: str = "start_date",
    variable_annuity_payment_mode: str = "reprice_on_reset",
    preserve_basis_for_non_risk_free: bool = True,
    apply_post_shock_floor: bool = True,
    source_specs: Sequence[Mapping[str, Any]] | None = None,
    build_monthly_chart: bool = True,
    chart_output_path: str | Path | None = None,
    monthly_chart_scenarios: Sequence[str] = ("base", "parallel-up", "parallel-down"),
) -> NIIPipelineResult:
    """
    Ejecuta NII desde inputs declarativos y genera (opcional) grafico mensual.

    Mantiene el calculo de NII exacto existente; el perfil mensual se deriva del
    mismo motor para reporting.

    `variable_annuity_payment_mode` controla el default global de
    variable_annuity cuando la columna `annuity_payment_mode` no viene en datos.
    Valores: "reprice_on_reset" | "fixed_payment".
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

    run_out: NIIMonthlyProfileResult = run_nii_12m_scenarios_with_monthly_profile(
        positions=positions,
        base_curve_set=base_curve_set,
        scenario_curve_sets=scenario_curve_sets,
        scheduled_principal_flows=scheduled_flows,
        risk_free_index=risk_free_index,
        balance_constant=balance_constant,
        margin_lookback_months=margin_lookback_months,
        margin_start_date_col=margin_start_date_col,
        months=NII_HORIZON_MONTHS,
        variable_annuity_payment_mode=variable_annuity_payment_mode,
    )

    out_chart_path: Path | None = None
    out_base_vs_worst_chart_path: Path | None = None
    if build_monthly_chart:
        if chart_output_path is None:
            out_chart_path = (
                Path.cwd()
                / "almready"
                / "tests"
                / "out"
                / "nii_monthly_base_parallel.png"
            )
        else:
            out_chart_path = Path(chart_output_path)

        plot_nii_monthly_profile(
            run_out.monthly_profile,
            output_path=out_chart_path,
            scenarios=tuple(str(s) for s in monthly_chart_scenarios),
            title_prefix="NII mensual (12M)",
        )

        if run_out.run_result.scenario_nii_12m:
            worst_scenario = min(
                run_out.run_result.scenario_nii_12m.keys(),
                key=lambda s: float(run_out.run_result.scenario_nii_12m[str(s)]),
            )
            if chart_output_path is None:
                out_base_vs_worst_chart_path = (
                    Path.cwd()
                    / "almready"
                    / "tests"
                    / "out"
                    / "nii_base_vs_worst_by_month.png"
                )
            else:
                p = Path(chart_output_path)
                out_base_vs_worst_chart_path = p.with_name(f"{p.stem}_base_vs_worst{p.suffix}")

            plot_nii_base_vs_worst_by_month(
                run_out.monthly_profile,
                worst_scenario=str(worst_scenario),
                output_path=out_base_vs_worst_chart_path,
                title=f"NII por mes: Base vs {worst_scenario}",
            )

    return NIIPipelineResult(
        analysis_date=analysis_date,
        base_nii_12m=float(run_out.run_result.base_nii_12m),
        scenario_nii_12m={k: float(v) for k, v in run_out.run_result.scenario_nii_12m.items()},
        monthly_profile=run_out.monthly_profile.copy(),
        chart_path=out_chart_path,
        chart_base_vs_worst_path=out_base_vs_worst_chart_path,
        positions_count=int(len(positions)),
        scheduled_flows_count=int(len(scheduled_flows)),
        excluded_source_contract_types=excluded_types,
    )
