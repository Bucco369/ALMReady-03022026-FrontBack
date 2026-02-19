from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from almready.services.margin_engine import CalibratedMarginSet, calibrate_margin_set
from almready.services.market import ForwardCurveSet
from almready.services.nii_projectors import (
    project_fixed_annuity_nii_12m,
    project_fixed_bullet_nii_12m,
    project_fixed_linear_nii_12m,
    project_fixed_scheduled_nii_12m,
    project_variable_annuity_nii_12m,
    project_variable_bullet_nii_12m,
    project_variable_linear_nii_12m,
    project_variable_scheduled_nii_12m,
)


@dataclass
class NIIRunResult:
    analysis_date: Any
    base_nii_12m: float
    scenario_nii_12m: dict[str, float]


@dataclass
class NIIMonthlyProfileResult:
    run_result: NIIRunResult
    monthly_profile: pd.DataFrame


_IMPLEMENTED_SOURCE_CONTRACT_TYPES = {
    "fixed_annuity",
    "fixed_bullet",
    "fixed_linear",
    "fixed_scheduled",
    "variable_annuity",
    "variable_bullet",
    "variable_linear",
    "variable_scheduled",
}
_EXCLUDED_SOURCE_CONTRACT_TYPES = {
    "static_position",
    "fixed_non_maturity",
    "variable_non_maturity",
}


def _normalise_source_contract_type(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip().str.lower()


def _split_implemented_positions(positions: pd.DataFrame) -> pd.DataFrame:
    """
    En esta fase soportamos fixed_annuity, fixed_bullet, fixed_linear,
    fixed_scheduled, variable_annuity, variable_bullet, variable_linear
    y variable_scheduled.
    Si viene source_contract_type, se valida explicitamente que no haya
    tipos no implementados (excepto static_position, que se excluye).
    """
    if positions.empty:
        return positions.copy()

    if "source_contract_type" in positions.columns:
        sct = _normalise_source_contract_type(positions["source_contract_type"])
        valid_non_empty = sct[sct != ""]
        unknown = sorted(
            set(valid_non_empty.unique().tolist())
            - _IMPLEMENTED_SOURCE_CONTRACT_TYPES
            - _EXCLUDED_SOURCE_CONTRACT_TYPES
        )
        if unknown:
            raise NotImplementedError(
                "NII MVP solo implementa source_contract_type en "
                "['fixed_annuity', 'fixed_bullet', 'fixed_linear', 'fixed_scheduled', "
                "'variable_annuity', 'variable_bullet', 'variable_linear', 'variable_scheduled']. "
                f"Tipos presentes no implementados: {unknown}"
            )

        mask = sct.isin(_IMPLEMENTED_SOURCE_CONTRACT_TYPES)
        return positions.loc[mask].copy()

    if "rate_type" not in positions.columns:
        raise ValueError(
            "positions no contiene 'source_contract_type' ni 'rate_type'; "
            "no se pueden identificar tipos NII implementados."
        )

    # Fallback cuando no hay source_contract_type:
    # asumimos:
    # - fixed + maturity_date -> fixed_bullet
    # - float + maturity_date -> variable_bullet
    mask = (
        positions["rate_type"].astype("string").str.strip().str.lower().isin({"fixed", "float"})
        & positions["maturity_date"].notna()
    )
    return positions.loc[mask].copy()


def compute_nii_margin_set(
    positions: pd.DataFrame,
    *,
    curve_set: ForwardCurveSet,
    risk_free_index: str = "EUR_ESTR_OIS",
    as_of=None,
    lookback_months: int | None = 12,
    start_date_col: str = "start_date",
) -> CalibratedMarginSet | None:
    """
    Public helper: calibrate the NII margin set from a positions DataFrame.

    Applies the same NII-eligibility filter as run_nii_12m_scenarios
    (via _split_implemented_positions) before delegating to calibrate_margin_set.
    Returns None if there are no eligible positions.

    Use this to pre-compute the margin set once before running multiple
    scenarios in parallel, so each worker receives the already-calibrated
    set instead of re-computing it independently.
    """
    nii_pos = _split_implemented_positions(positions)
    if nii_pos.empty:
        return None
    return calibrate_margin_set(
        nii_pos,
        curve_set=curve_set,
        risk_free_index=risk_free_index,
        as_of=as_of,
        lookback_months=lookback_months,
        start_date_col=start_date_col,
    )


def run_nii_12m_base(
    positions: pd.DataFrame,
    curve_set: ForwardCurveSet,
    *,
    scheduled_principal_flows: pd.DataFrame | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    margin_lookback_months: int | None = 12,
    margin_start_date_col: str = "start_date",
    horizon_months: int = 12,
    variable_annuity_payment_mode: str = "reprice_on_reset",
) -> float:
    """
    MVP actual: NII 12m para fixed_annuity, fixed_bullet, fixed_linear,
    fixed_scheduled, variable_annuity, variable_bullet, variable_linear
    y variable_scheduled.
    """
    nii_positions = _split_implemented_positions(positions)
    if nii_positions.empty:
        return 0.0

    effective_margin_set = margin_set
    if effective_margin_set is None and balance_constant:
        effective_margin_set = calibrate_margin_set(
            nii_positions,
            curve_set=curve_set,
            risk_free_index=risk_free_index,
            as_of=curve_set.analysis_date,
            lookback_months=margin_lookback_months,
            start_date_col=margin_start_date_col,
        )

    if "source_contract_type" in nii_positions.columns:
        sct = _normalise_source_contract_type(nii_positions["source_contract_type"])
        fixed_annuity_positions = nii_positions.loc[sct.eq("fixed_annuity")].copy()
        fixed_positions = nii_positions.loc[sct.eq("fixed_bullet")].copy()
        fixed_linear_positions = nii_positions.loc[sct.eq("fixed_linear")].copy()
        fixed_scheduled_positions = nii_positions.loc[sct.eq("fixed_scheduled")].copy()
        variable_annuity_positions = nii_positions.loc[sct.eq("variable_annuity")].copy()
        variable_bullet_positions = nii_positions.loc[sct.eq("variable_bullet")].copy()
        variable_linear_positions = nii_positions.loc[sct.eq("variable_linear")].copy()
        variable_scheduled_positions = nii_positions.loc[sct.eq("variable_scheduled")].copy()
    else:
        rt = nii_positions["rate_type"].astype("string").str.strip().str.lower()
        fixed_annuity_positions = nii_positions.iloc[0:0].copy()
        fixed_positions = nii_positions.loc[rt.eq("fixed")].copy()
        fixed_linear_positions = nii_positions.iloc[0:0].copy()
        fixed_scheduled_positions = nii_positions.iloc[0:0].copy()
        variable_annuity_positions = nii_positions.iloc[0:0].copy()
        variable_bullet_positions = nii_positions.loc[rt.eq("float")].copy()
        variable_linear_positions = nii_positions.iloc[0:0].copy()
        variable_scheduled_positions = nii_positions.iloc[0:0].copy()

    has_scheduled = (not fixed_scheduled_positions.empty) or (not variable_scheduled_positions.empty)
    if has_scheduled and scheduled_principal_flows is None:
        raise ValueError(
            "Se han recibido posiciones scheduled pero falta scheduled_principal_flows. "
            "Carga contract+payment con io.scheduled_reader.load_scheduled_from_specs."
        )

    out = 0.0
    if not fixed_annuity_positions.empty:
        out += project_fixed_annuity_nii_12m(
            fixed_annuity_positions,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            risk_free_index=risk_free_index,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
        )
    if not fixed_positions.empty:
        out += project_fixed_bullet_nii_12m(
            fixed_positions,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            risk_free_index=risk_free_index,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
        )
    if not fixed_linear_positions.empty:
        out += project_fixed_linear_nii_12m(
            fixed_linear_positions,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            risk_free_index=risk_free_index,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
        )
    if not fixed_scheduled_positions.empty:
        out += project_fixed_scheduled_nii_12m(
            fixed_scheduled_positions,
            principal_flows=scheduled_principal_flows,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            risk_free_index=risk_free_index,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
        )
    if not variable_bullet_positions.empty:
        out += project_variable_bullet_nii_12m(
            variable_bullet_positions,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
        )
    if not variable_annuity_positions.empty:
        out += project_variable_annuity_nii_12m(
            variable_annuity_positions,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
            annuity_payment_mode=variable_annuity_payment_mode,
        )
    if not variable_scheduled_positions.empty:
        out += project_variable_scheduled_nii_12m(
            variable_scheduled_positions,
            principal_flows=scheduled_principal_flows,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
        )
    if not variable_linear_positions.empty:
        out += project_variable_linear_nii_12m(
            variable_linear_positions,
            analysis_date=curve_set.analysis_date,
            curve_set=curve_set,
            margin_set=effective_margin_set,
            balance_constant=balance_constant,
            horizon_months=horizon_months,
        )
    return float(out)


def run_nii_12m_scenarios(
    positions: pd.DataFrame,
    base_curve_set: ForwardCurveSet,
    scenario_curve_sets: dict[str, ForwardCurveSet],
    *,
    scheduled_principal_flows: pd.DataFrame | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    margin_lookback_months: int | None = 12,
    margin_start_date_col: str = "start_date",
    horizon_months: int = 12,
    variable_annuity_payment_mode: str = "reprice_on_reset",
) -> NIIRunResult:
    """
    Orquestacion base + escenarios para NII 12m.
    En esta fase soporta fixed_annuity, fixed_bullet, fixed_linear,
    fixed_scheduled, variable_annuity, variable_bullet, variable_linear
    y variable_scheduled.
    """
    nii_positions = _split_implemented_positions(positions)

    effective_margin_set = margin_set
    if effective_margin_set is None and balance_constant and not nii_positions.empty:
        effective_margin_set = calibrate_margin_set(
            nii_positions,
            curve_set=base_curve_set,
            risk_free_index=risk_free_index,
            as_of=base_curve_set.analysis_date,
            lookback_months=margin_lookback_months,
            start_date_col=margin_start_date_col,
        )

    base_nii = run_nii_12m_base(
        positions,
        base_curve_set,
        scheduled_principal_flows=scheduled_principal_flows,
        margin_set=effective_margin_set,
        risk_free_index=risk_free_index,
        balance_constant=balance_constant,
        margin_lookback_months=margin_lookback_months,
        margin_start_date_col=margin_start_date_col,
        horizon_months=horizon_months,
        variable_annuity_payment_mode=variable_annuity_payment_mode,
    )

    scenario_values: dict[str, float] = {}
    for scenario_name, scenario_curve_set in scenario_curve_sets.items():
        scenario_values[str(scenario_name)] = run_nii_12m_base(
            positions,
            scenario_curve_set,
            scheduled_principal_flows=scheduled_principal_flows,
            margin_set=effective_margin_set,
            risk_free_index=risk_free_index,
            balance_constant=balance_constant,
            margin_lookback_months=margin_lookback_months,
            margin_start_date_col=margin_start_date_col,
            horizon_months=horizon_months,
            variable_annuity_payment_mode=variable_annuity_payment_mode,
        )

    return NIIRunResult(
        analysis_date=base_curve_set.analysis_date,
        base_nii_12m=float(base_nii),
        scenario_nii_12m=scenario_values,
    )


def build_nii_monthly_profile(
    positions: pd.DataFrame,
    base_curve_set: ForwardCurveSet,
    scenario_curve_sets: dict[str, ForwardCurveSet],
    *,
    scheduled_principal_flows: pd.DataFrame | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    margin_lookback_months: int | None = 12,
    margin_start_date_col: str = "start_date",
    months: int = 12,
    variable_annuity_payment_mode: str = "reprice_on_reset",
) -> pd.DataFrame:
    """
    Perfil mensual de NII por escenario.

    Columnas:
    - scenario
    - month_index (1..months)
    - month_label (1M..12M)
    - interest_income (activo, esperado positivo)
    - interest_expense (pasivo, esperado negativo)
    - net_nii
    """
    m = int(months)
    if m <= 0:
        raise ValueError("months debe ser > 0")

    nii_positions = _split_implemented_positions(positions)
    if nii_positions.empty:
        return pd.DataFrame(
            columns=[
                "scenario",
                "month_index",
                "month_label",
                "interest_income",
                "interest_expense",
                "net_nii",
            ]
        )

    effective_margin_set = margin_set
    if effective_margin_set is None and balance_constant:
        effective_margin_set = calibrate_margin_set(
            nii_positions,
            curve_set=base_curve_set,
            risk_free_index=risk_free_index,
            as_of=base_curve_set.analysis_date,
            lookback_months=margin_lookback_months,
            start_date_col=margin_start_date_col,
        )

    if "side" in nii_positions.columns:
        side_tokens = (
            nii_positions["side"]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
        )
        asset_positions = nii_positions.loc[side_tokens.eq("A")].copy()
        liability_positions = nii_positions.loc[side_tokens.eq("L")].copy()
    else:
        asset_positions = nii_positions.copy()
        liability_positions = nii_positions.iloc[0:0].copy()

    scenario_items: list[tuple[str, ForwardCurveSet]] = [("base", base_curve_set)]
    for scenario_name, scenario_curve_set in scenario_curve_sets.items():
        scenario_items.append((str(scenario_name), scenario_curve_set))

    rows: list[dict[str, Any]] = []
    for scenario_name, curve_set in scenario_items:
        prev_income_cum = 0.0
        prev_expense_cum = 0.0

        for month_idx in range(1, m + 1):
            income_cum = run_nii_12m_base(
                asset_positions,
                curve_set,
                scheduled_principal_flows=scheduled_principal_flows,
                margin_set=effective_margin_set,
                risk_free_index=risk_free_index,
                balance_constant=balance_constant,
                margin_lookback_months=margin_lookback_months,
                margin_start_date_col=margin_start_date_col,
                horizon_months=month_idx,
                variable_annuity_payment_mode=variable_annuity_payment_mode,
            )
            expense_cum = run_nii_12m_base(
                liability_positions,
                curve_set,
                scheduled_principal_flows=scheduled_principal_flows,
                margin_set=effective_margin_set,
                risk_free_index=risk_free_index,
                balance_constant=balance_constant,
                margin_lookback_months=margin_lookback_months,
                margin_start_date_col=margin_start_date_col,
                horizon_months=month_idx,
                variable_annuity_payment_mode=variable_annuity_payment_mode,
            )

            income_month = float(income_cum - prev_income_cum)
            expense_month = float(expense_cum - prev_expense_cum)
            net_month = float(income_month + expense_month)

            rows.append(
                {
                    "scenario": str(scenario_name),
                    "month_index": int(month_idx),
                    "month_label": f"{int(month_idx)}M",
                    "interest_income": income_month,
                    "interest_expense": expense_month,
                    "net_nii": net_month,
                }
            )

            prev_income_cum = float(income_cum)
            prev_expense_cum = float(expense_cum)

    return pd.DataFrame(rows)


def run_nii_12m_scenarios_with_monthly_profile(
    positions: pd.DataFrame,
    base_curve_set: ForwardCurveSet,
    scenario_curve_sets: dict[str, ForwardCurveSet],
    *,
    scheduled_principal_flows: pd.DataFrame | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    margin_lookback_months: int | None = 12,
    margin_start_date_col: str = "start_date",
    months: int = 12,
    variable_annuity_payment_mode: str = "reprice_on_reset",
) -> NIIMonthlyProfileResult:
    run_result = run_nii_12m_scenarios(
        positions=positions,
        base_curve_set=base_curve_set,
        scenario_curve_sets=scenario_curve_sets,
        scheduled_principal_flows=scheduled_principal_flows,
        margin_set=margin_set,
        risk_free_index=risk_free_index,
        balance_constant=balance_constant,
        margin_lookback_months=margin_lookback_months,
        margin_start_date_col=margin_start_date_col,
        horizon_months=max(12, int(months)),
        variable_annuity_payment_mode=variable_annuity_payment_mode,
    )

    monthly_profile = build_nii_monthly_profile(
        positions=positions,
        base_curve_set=base_curve_set,
        scenario_curve_sets=scenario_curve_sets,
        scheduled_principal_flows=scheduled_principal_flows,
        margin_set=margin_set,
        risk_free_index=risk_free_index,
        balance_constant=balance_constant,
        margin_lookback_months=margin_lookback_months,
        margin_start_date_col=margin_start_date_col,
        months=months,
        variable_annuity_payment_mode=variable_annuity_payment_mode,
    )

    return NIIMonthlyProfileResult(
        run_result=run_result,
        monthly_profile=monthly_profile,
    )
