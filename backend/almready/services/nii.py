from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from dateutil.relativedelta import relativedelta

from almready.config import NII_HORIZON_MONTHS
from almready.core.daycount import normalizar_base_de_calculo, yearfrac
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
        horizon_months=int(months),
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


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED NII FROM EVE CASHFLOWS
# Derives aggregate + monthly NII from the same cashflows used for EVE,
# eliminating the need for separate NII projector calls and the 24x monthly
# profile computation.
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NiiFromCashflowsResult:
    aggregate_nii: float
    asset_nii: float
    liability_nii: float
    monthly_breakdown: list[dict]


def _prorate_to_months(
    interest: float,
    period_start: date,
    period_end: date,
    analysis_date: date,
    horizon_months: int,
    is_asset: bool,
    monthly: dict[int, dict[str, float]],
    month_bounds: list[date] | None = None,
) -> None:
    """Pro-rate a signed interest amount across calendar months by day count."""
    if abs(interest) < 1e-16 or period_end <= period_start:
        return
    total_days = (period_end - period_start).days
    if total_days <= 0:
        return
    key = "income" if is_asset else "expense"
    # OPT-2: Narrow loop to only relevant months
    first_mi = max(
        1,
        (period_start.year - analysis_date.year) * 12
        + period_start.month - analysis_date.month,
    )
    last_mi = min(
        horizon_months,
        (period_end.year - analysis_date.year) * 12
        + period_end.month - analysis_date.month + 1,
    )
    for mi in range(max(1, first_mi), last_mi + 1):
        # OPT-5: Use pre-computed boundaries if available
        if month_bounds is not None:
            m_start = month_bounds[mi - 1]
            m_end = month_bounds[mi]
        else:
            m_start = analysis_date + relativedelta(months=mi - 1)
            m_end = analysis_date + relativedelta(months=mi)
        overlap_start = max(period_start, m_start)
        overlap_end = min(period_end, m_end)
        overlap_days = (overlap_end - overlap_start).days
        if overlap_days > 0:
            monthly[mi][key] += interest * overlap_days / total_days


def _monthly_to_list(
    monthly: dict[int, dict[str, float]],
    horizon_months: int,
) -> list[dict]:
    """Convert monthly accumulators to the standard list format."""
    out: list[dict] = []
    for mi in range(1, horizon_months + 1):
        vals = monthly[mi]
        out.append({
            "month_index": mi,
            "month_label": f"{mi}M",
            "interest_income": vals["income"],
            "interest_expense": vals["expense"],
            "net_nii": vals["income"] + vals["expense"],
        })
    return out


def _compute_renewal_nii(
    pos_row,
    contract_id: str,
    sct: str,
    curve_set: ForwardCurveSet,
    analysis_date: date,
    horizon_end: date,
    horizon_months: int,
    notional: float,
    sign: float,
    base: str,
    is_asset: bool,
    margin_set: CalibratedMarginSet | None,
    risk_free_index: str,
    positions_df: pd.DataFrame,
    scheduled_principal_flows: pd.DataFrame | None,
    monthly: dict[int, dict[str, float]],
    month_bounds: list[date] | None = None,
    rate_cache: dict[tuple[str, date], float] | None = None,
) -> float:
    """Compute renewal NII for a single contract that matures before horizon_end.

    Mutates *monthly* in-place and returns the total renewal NII (signed).
    """
    # OPT-4: Cached rate lookup to avoid redundant curve interpolation
    def _rate(index_name: str, d: date) -> float:
        if rate_cache is not None:
            key = (index_name, d)
            if key not in rate_cache:
                rate_cache[key] = float(curve_set.rate_on_date(index_name, d))
            return rate_cache[key]
        return float(curve_set.rate_on_date(index_name, d))

    from almready.services.nii_projectors import (
        add_frequency,
        coerce_date,
        coerce_float,
        cycle_maturity,
        is_blank,
        linear_notional_at,
        lookup_margin_for_row,
        normalise_annuity_payment_mode,
        original_term_days,
        parse_frequency_token,
        payment_frequency_or_default,
        prepare_scheduled_principal_flows,
        project_fixed_annuity_cycle,
        project_fixed_scheduled_cycle,
        project_variable_annuity_cycle,
        project_variable_bullet_cycle,
        project_variable_linear_cycle,
        project_variable_scheduled_cycle,
        scheduled_flow_map_from_template,
        scheduled_template_from_remaining_flows,
        template_term_days,
    )

    start_date = coerce_date(
        getattr(pos_row, "start_date"), field_name="start_date", row_id=contract_id
    )
    maturity_date = coerce_date(
        getattr(pos_row, "maturity_date"), field_name="maturity_date", row_id=contract_id
    )
    term_days = original_term_days(start_date, maturity_date)
    total_nii = 0.0

    # ── Helper: extract variable-rate fields from row ──
    def _var_fields():
        spread = coerce_float(
            getattr(pos_row, "spread"), field_name="spread", row_id=contract_id
        )
        index_name = str(getattr(pos_row, "index_name", "")).strip()
        floor_rate = getattr(pos_row, "floor_rate", None)
        cap_rate = getattr(pos_row, "cap_rate", None)
        freq = None
        if "repricing_freq" in positions_df.columns:
            freq = parse_frequency_token(
                getattr(pos_row, "repricing_freq", None), row_id=contract_id
            )
        return spread, index_name, floor_rate, cap_rate, freq

    # ── FIXED BULLET ──
    if sct == "fixed_bullet":
        fixed_rate = coerce_float(
            getattr(pos_row, "fixed_rate"), field_name="fixed_rate", row_id=contract_id
        )
        margin_default = fixed_rate - _rate(risk_free_index, maturity_date)
        renewal_margin = lookup_margin_for_row(
            row=pos_row, rate_type="fixed",
            margin_set=margin_set, default_margin=margin_default,
        )
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = _rate(risk_free_index, cycle_maturity)
            renew_rate = rf + renewal_margin
            nii = sign * notional * renew_rate * yearfrac(cycle_start, cycle_end, base)
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    # ── FIXED ANNUITY ──
    elif sct == "fixed_annuity":
        fixed_rate = coerce_float(
            getattr(pos_row, "fixed_rate"), field_name="fixed_rate", row_id=contract_id
        )
        payment_frequency = payment_frequency_or_default(pos_row, row_id=contract_id)
        margin_default = fixed_rate - _rate(risk_free_index, maturity_date)
        renewal_margin = lookup_margin_for_row(
            row=pos_row, rate_type="fixed",
            margin_set=margin_set, default_margin=margin_default,
        )
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = _rate(risk_free_index, cycle_maturity)
            renew_rate = rf + renewal_margin
            nii = project_fixed_annuity_cycle(
                cycle_start=cycle_start, cycle_end=cycle_end,
                cycle_maturity=cycle_maturity, outstanding=notional,
                sign=sign, base=base, fixed_rate=renew_rate,
                payment_frequency=payment_frequency,
            )
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    # ── FIXED LINEAR ──
    elif sct == "fixed_linear":
        fixed_rate = coerce_float(
            getattr(pos_row, "fixed_rate"), field_name="fixed_rate", row_id=contract_id
        )
        margin_default = fixed_rate - _rate(risk_free_index, maturity_date)
        renewal_margin = lookup_margin_for_row(
            row=pos_row, rate_type="fixed",
            margin_set=margin_set, default_margin=margin_default,
        )
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = _rate(risk_free_index, cycle_maturity)
            renew_rate = rf + renewal_margin
            n0 = linear_notional_at(
                cycle_start, effective_start=cycle_start,
                maturity_date=cycle_maturity,
                outstanding_at_effective_start=notional,
            )
            n1 = linear_notional_at(
                cycle_end, effective_start=cycle_start,
                maturity_date=cycle_maturity,
                outstanding_at_effective_start=notional,
            )
            avg_not = 0.5 * (n0 + n1)
            nii = sign * avg_not * renew_rate * yearfrac(cycle_start, cycle_end, base)
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    # ── VARIABLE BULLET ──
    elif sct == "variable_bullet":
        spread, index_name, floor_rate, cap_rate, frequency = _var_fields()
        renewal_spread = lookup_margin_for_row(
            row=pos_row, rate_type="float",
            margin_set=margin_set, default_margin=spread,
        )
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)
            nii = project_variable_bullet_cycle(
                cycle_start=cycle_start, cycle_end=cycle_end,
                notional=notional, sign=sign, base=base,
                index_name=index_name, spread=renewal_spread,
                floor_rate=floor_rate, cap_rate=cap_rate,
                curve_set=curve_set, anchor_date=renewal_anchor,
                frequency=frequency, fixed_rate_for_stub=None,
            )
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    # ── VARIABLE ANNUITY ──
    elif sct == "variable_annuity":
        spread, index_name, floor_rate, cap_rate, frequency = _var_fields()
        renewal_spread = lookup_margin_for_row(
            row=pos_row, rate_type="float",
            margin_set=margin_set, default_margin=spread,
        )
        payment_frequency = payment_frequency_or_default(pos_row, row_id=contract_id)
        annuity_mode = "reprice_on_reset"
        if "annuity_payment_mode" in positions_df.columns and not is_blank(
            getattr(pos_row, "annuity_payment_mode", None)
        ):
            annuity_mode = normalise_annuity_payment_mode(
                getattr(pos_row, "annuity_payment_mode", None), row_id=contract_id,
            )
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)
            nii = project_variable_annuity_cycle(
                cycle_start=cycle_start, cycle_end=cycle_end,
                cycle_maturity=cycle_maturity, outstanding=notional,
                sign=sign, base=base, curve_set=curve_set,
                index_name=index_name, spread=renewal_spread,
                floor_rate=floor_rate, cap_rate=cap_rate,
                payment_frequency=payment_frequency,
                anchor_date=renewal_anchor,
                repricing_frequency=frequency,
                fixed_rate_for_stub=None,
                annuity_payment_mode=annuity_mode,
            )
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    # ── VARIABLE LINEAR ──
    elif sct == "variable_linear":
        spread, index_name, floor_rate, cap_rate, frequency = _var_fields()
        renewal_spread = lookup_margin_for_row(
            row=pos_row, rate_type="float",
            margin_set=margin_set, default_margin=spread,
        )
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)
            nii = project_variable_linear_cycle(
                cycle_start=cycle_start, cycle_end=cycle_end,
                cycle_maturity=cycle_maturity, outstanding=notional,
                sign=sign, base=base, index_name=index_name,
                spread=renewal_spread, floor_rate=floor_rate,
                cap_rate=cap_rate, curve_set=curve_set,
                anchor_date=renewal_anchor, frequency=frequency,
                fixed_rate_for_stub=None,
            )
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    # ── FIXED SCHEDULED ──
    elif sct == "fixed_scheduled":
        fixed_rate = coerce_float(
            getattr(pos_row, "fixed_rate"), field_name="fixed_rate", row_id=contract_id
        )
        margin_default = fixed_rate - _rate(risk_free_index, maturity_date)
        renewal_margin = lookup_margin_for_row(
            row=pos_row, rate_type="fixed",
            margin_set=margin_set, default_margin=margin_default,
        )
        accrual_start = max(start_date, analysis_date)
        flows_by_contract = prepare_scheduled_principal_flows(scheduled_principal_flows)
        contract_flows = flows_by_contract.get(contract_id, [])
        template = scheduled_template_from_remaining_flows(
            contract_flows,
            accrual_start=accrual_start,
            maturity_date=maturity_date,
            outstanding=notional,
        )
        sched_term_days = template_term_days(template)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, sched_term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = _rate(risk_free_index, cycle_maturity)
            renew_rate = rf + renewal_margin
            flow_map = scheduled_flow_map_from_template(
                cycle_start=cycle_start, cycle_end=cycle_end, template=template,
            )
            nii = project_fixed_scheduled_cycle(
                cycle_start=cycle_start, cycle_end=cycle_end,
                outstanding=notional, sign=sign, base=base,
                fixed_rate=renew_rate, principal_flow_map=flow_map,
            )
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    # ── VARIABLE SCHEDULED ──
    elif sct == "variable_scheduled":
        spread, index_name, floor_rate, cap_rate, frequency = _var_fields()
        renewal_spread = lookup_margin_for_row(
            row=pos_row, rate_type="float",
            margin_set=margin_set, default_margin=spread,
        )
        accrual_start = max(start_date, analysis_date)
        flows_by_contract = prepare_scheduled_principal_flows(scheduled_principal_flows)
        contract_flows = flows_by_contract.get(contract_id, [])
        template = scheduled_template_from_remaining_flows(
            contract_flows,
            accrual_start=accrual_start,
            maturity_date=maturity_date,
            outstanding=notional,
        )
        sched_term_days = template_term_days(template)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = cycle_maturity(cycle_start, sched_term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)
            flow_map = scheduled_flow_map_from_template(
                cycle_start=cycle_start, cycle_end=cycle_end, template=template,
            )
            nii = project_variable_scheduled_cycle(
                cycle_start=cycle_start, cycle_end=cycle_end,
                outstanding=notional, sign=sign, base=base,
                curve_set=curve_set, index_name=index_name,
                spread=renewal_spread, floor_rate=floor_rate,
                cap_rate=cap_rate, anchor_date=renewal_anchor,
                frequency=frequency, fixed_rate_for_stub=None,
                principal_flow_map=flow_map,
            )
            total_nii += nii
            _prorate_to_months(
                nii, cycle_start, cycle_end, analysis_date, horizon_months, is_asset, monthly,
                month_bounds,
            )
            cycle_start = cycle_maturity

    return total_nii


def compute_nii_from_cashflows(
    cashflows_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    curve_set: ForwardCurveSet,
    *,
    analysis_date: date,
    horizon_months: int = NII_HORIZON_MONTHS,
    balance_constant: bool = True,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    scheduled_principal_flows: pd.DataFrame | None = None,
) -> NiiFromCashflowsResult:
    """Derive NII (aggregate + monthly) from EVE cashflows.

    Pre-maturity interest is read directly from the cashflow DataFrame.
    End-of-horizon stubs and balance_constant renewals are computed from
    position metadata.  Monthly breakdown uses day-proportional pro-rating
    of each coupon's interest across calendar months.
    """
    from almready.services.nii_projectors import (
        coerce_date,
        coerce_float,
        is_blank,
        parse_frequency_token,
        project_variable_bullet_cycle,
        side_sign,
    )

    horizon_end = analysis_date + relativedelta(months=horizon_months)

    # OPT-5: Pre-compute month boundaries once (avoids ~120k relativedelta calls)
    month_bounds: list[date] = [
        analysis_date + relativedelta(months=i) for i in range(horizon_months + 1)
    ]

    # OPT-4: Shared rate cache across all renewal computations
    rate_cache: dict[tuple[str, date], float] = {}

    monthly: dict[int, dict[str, float]] = {
        mi: {"income": 0.0, "expense": 0.0}
        for mi in range(1, horizon_months + 1)
    }

    empty_result = NiiFromCashflowsResult(
        aggregate_nii=0.0, asset_nii=0.0, liability_nii=0.0,
        monthly_breakdown=_monthly_to_list(monthly, horizon_months),
    )

    # Filter NII-eligible positions
    nii_positions = _split_implemented_positions(positions_df)
    if nii_positions.empty:
        return empty_result

    # Build position lookup by contract_id
    pos_lookup: dict[str, Any] = {}
    for row in nii_positions.itertuples(index=False):
        cid = str(getattr(row, "contract_id", "")).strip()
        if cid:
            pos_lookup[cid] = row

    nii_contract_ids = set(pos_lookup.keys())
    total_income = 0.0
    total_expense = 0.0
    processed_contracts: set[str] = set()

    # ── Process contracts that have EVE cashflows ─────────────────────────
    if not cashflows_df.empty:
        cf = cashflows_df[cashflows_df["contract_id"].isin(nii_contract_ids)].copy()
        if not cf.empty:
            cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce").dt.date

            # ── OPT-6: Vectorized Section A (pre-maturity NII) ────────
            import numpy as np

            side_is_asset_map: dict[str, bool] = {}
            accrual_start_map: dict[str, date] = {}
            for _cid, _pos in pos_lookup.items():
                side_is_asset_map[_cid] = (
                    str(getattr(_pos, "side", "A")).strip().upper() == "A"
                )
                _sd = coerce_date(
                    getattr(_pos, "start_date"),
                    field_name="start_date", row_id=_cid,
                )
                accrual_start_map[_cid] = max(_sd, analysis_date)

            cf_sorted = cf.sort_values(["contract_id", "flow_date"])
            cf_horizon = cf_sorted[cf_sorted["flow_date"] <= horizon_end].copy()

            if not cf_horizon.empty:
                cf_horizon["is_asset"] = cf_horizon["contract_id"].map(
                    side_is_asset_map
                )
                cf_horizon["accrual_start"] = cf_horizon["contract_id"].map(
                    accrual_start_map
                )

                # prev_date: previous flow within same contract, or accrual_start
                cf_horizon["prev_date"] = cf_horizon.groupby(
                    "contract_id"
                )["flow_date"].shift(1)
                first_mask = cf_horizon["prev_date"].isna()
                cf_horizon.loc[first_mask, "prev_date"] = cf_horizon.loc[
                    first_mask, "accrual_start"
                ]

                # Scalar totals (vectorized)
                interest_col = cf_horizon["interest_amount"].astype(float)
                sig_mask = interest_col.abs() > 1e-16
                asset_mask = cf_horizon["is_asset"].fillna(True)
                total_income = float(
                    interest_col[sig_mask & asset_mask].sum()
                )
                total_expense = float(
                    interest_col[sig_mask & ~asset_mask].sum()
                )

                # Monthly pro-rating (vectorized via numpy ordinals)
                cf_sig = cf_horizon[sig_mask]
                if not cf_sig.empty:
                    interest_arr = cf_sig["interest_amount"].astype(float).values
                    flow_ord = np.array(
                        [d.toordinal() for d in cf_sig["flow_date"]]
                    )
                    prev_ord = np.array(
                        [d.toordinal() for d in cf_sig["prev_date"]]
                    )
                    total_days_arr = flow_ord - prev_ord
                    valid_mask = total_days_arr > 0
                    if valid_mask.any():
                        int_v = interest_arr[valid_mask]
                        flow_v = flow_ord[valid_mask]
                        prev_v = prev_ord[valid_mask]
                        days_v = total_days_arr[valid_mask]
                        asset_v = cf_sig["is_asset"].values[valid_mask]

                        for mi in range(1, horizon_months + 1):
                            ms = month_bounds[mi - 1].toordinal()
                            me = month_bounds[mi].toordinal()
                            ol_s = np.maximum(prev_v, ms)
                            ol_e = np.minimum(flow_v, me)
                            ol_d = np.maximum(0, ol_e - ol_s)
                            contrib = int_v * ol_d / days_v
                            monthly[mi]["income"] += float(
                                contrib[asset_v].sum()
                            )
                            monthly[mi]["expense"] += float(
                                contrib[~asset_v].sum()
                            )

            # Pre-compute per-contract aggregates for Sections B and C
            last_flow_date_map: dict[str, date] = {}
            cum_principal_map: dict[str, float] = {}
            if not cf_horizon.empty:
                for _cid_raw, _grp in cf_horizon.groupby("contract_id"):
                    _cs = str(_cid_raw)
                    last_flow_date_map[_cs] = _grp["flow_date"].iloc[-1]
                    cum_principal_map[_cs] = float(
                        _grp["principal_amount"].abs().sum()
                    )

            # ── Per-contract loop for Sections B (stub) and C (renewal) ───
            for contract_id_raw in cf["contract_id"].unique():
                cid = str(contract_id_raw)
                if cid not in pos_lookup:
                    continue
                processed_contracts.add(cid)
                pos = pos_lookup[cid]

                side = str(getattr(pos, "side", "A")).strip().upper()
                is_asset = side == "A"
                sct = str(getattr(pos, "source_contract_type", "")).strip().lower()

                maturity_date = coerce_date(
                    getattr(pos, "maturity_date"),
                    field_name="maturity_date", row_id=cid,
                )
                start_date = coerce_date(
                    getattr(pos, "start_date"),
                    field_name="start_date", row_id=cid,
                )
                notional = abs(coerce_float(
                    getattr(pos, "notional"),
                    field_name="notional", row_id=cid,
                ))
                base = normalizar_base_de_calculo(str(getattr(pos, "daycount_base")))
                sign = side_sign(getattr(pos, "side"), row_id=cid)

                accrual_start = accrual_start_map.get(
                    cid, max(start_date, analysis_date)
                )
                prev_date = last_flow_date_map.get(cid, accrual_start)

                # ── B. End-of-horizon stub ────────────────────────────────
                if maturity_date > horizon_end:
                    stub_start = prev_date
                    if stub_start < horizon_end:
                        cum_principal = cum_principal_map.get(cid, 0.0)
                        balance = max(0.0, notional - cum_principal)
                        if balance > 1e-10:
                            is_variable = sct.startswith("variable_")
                            if is_variable:
                                # Use variable bullet cycle for correct reset handling
                                spread = coerce_float(
                                    getattr(pos, "spread"),
                                    field_name="spread", row_id=cid,
                                )
                                index_name = str(getattr(pos, "index_name", "")).strip()
                                floor_rate = getattr(pos, "floor_rate", None)
                                cap_rate = getattr(pos, "cap_rate", None)
                                fixed_rate_stub = None
                                if not is_blank(getattr(pos, "fixed_rate", None)):
                                    fixed_rate_stub = coerce_float(
                                        getattr(pos, "fixed_rate"),
                                        field_name="fixed_rate", row_id=cid,
                                    )
                                anchor_date = None
                                if "next_reprice_date" in nii_positions.columns and not is_blank(
                                    getattr(pos, "next_reprice_date", None)
                                ):
                                    anchor_date = coerce_date(
                                        getattr(pos, "next_reprice_date"),
                                        field_name="next_reprice_date", row_id=cid,
                                    )
                                frequency = None
                                if "repricing_freq" in nii_positions.columns:
                                    frequency = parse_frequency_token(
                                        getattr(pos, "repricing_freq", None),
                                        row_id=cid,
                                    )
                                stub_nii = project_variable_bullet_cycle(
                                    cycle_start=stub_start,
                                    cycle_end=horizon_end,
                                    notional=balance, sign=sign, base=base,
                                    index_name=index_name, spread=spread,
                                    floor_rate=floor_rate, cap_rate=cap_rate,
                                    curve_set=curve_set,
                                    anchor_date=anchor_date,
                                    frequency=frequency,
                                    fixed_rate_for_stub=fixed_rate_stub,
                                )
                            else:
                                fixed_rate = coerce_float(
                                    getattr(pos, "fixed_rate"),
                                    field_name="fixed_rate", row_id=cid,
                                )
                                stub_nii = sign * balance * fixed_rate * yearfrac(
                                    stub_start, horizon_end, base
                                )

                            if abs(stub_nii) > 1e-16:
                                _prorate_to_months(
                                    stub_nii, stub_start, horizon_end,
                                    analysis_date, horizon_months, is_asset, monthly,
                                    month_bounds,
                                )
                                if is_asset:
                                    total_income += stub_nii
                                else:
                                    total_expense += stub_nii

                # ── C. Renewal NII ────────────────────────────────────────
                if balance_constant and maturity_date < horizon_end:
                    renewal_nii = _compute_renewal_nii(
                        pos, cid, sct, curve_set, analysis_date, horizon_end,
                        horizon_months, notional, sign, base, is_asset,
                        margin_set, risk_free_index, nii_positions,
                        scheduled_principal_flows, monthly,
                        month_bounds, rate_cache,
                    )
                    if is_asset:
                        total_income += renewal_nii
                    else:
                        total_expense += renewal_nii

    # ── Process positions with NO EVE cashflows (need renewals only) ──────
    if balance_constant:
        for cid, pos in pos_lookup.items():
            if cid in processed_contracts:
                continue
            maturity_date = coerce_date(
                getattr(pos, "maturity_date"),
                field_name="maturity_date", row_id=cid,
            )
            if maturity_date <= analysis_date or maturity_date >= horizon_end:
                continue
            # Pre-maturity interest for very short-lived positions
            start_date = coerce_date(
                getattr(pos, "start_date"),
                field_name="start_date", row_id=cid,
            )
            accrual_start = max(start_date, analysis_date)
            accrual_end = min(maturity_date, horizon_end)
            if accrual_end > accrual_start:
                sct = str(getattr(pos, "source_contract_type", "")).strip().lower()
                notional = abs(coerce_float(
                    getattr(pos, "notional"), field_name="notional", row_id=cid,
                ))
                base = normalizar_base_de_calculo(str(getattr(pos, "daycount_base")))
                sign = side_sign(getattr(pos, "side"), row_id=cid)
                side = str(getattr(pos, "side", "A")).strip().upper()
                is_asset = side == "A"

                # Simple pre-maturity accrual (position had no EVE cashflows,
                # meaning it likely matures before the first coupon date)
                is_variable = sct.startswith("variable_")
                if is_variable:
                    spread = coerce_float(
                        getattr(pos, "spread"), field_name="spread", row_id=cid,
                    )
                    index_name = str(getattr(pos, "index_name", "")).strip()
                    floor_rate = getattr(pos, "floor_rate", None)
                    cap_rate = getattr(pos, "cap_rate", None)
                    fixed_rate_stub = None
                    if not is_blank(getattr(pos, "fixed_rate", None)):
                        fixed_rate_stub = coerce_float(
                            getattr(pos, "fixed_rate"),
                            field_name="fixed_rate", row_id=cid,
                        )
                    anchor_date = None
                    if "next_reprice_date" in nii_positions.columns and not is_blank(
                        getattr(pos, "next_reprice_date", None)
                    ):
                        anchor_date = coerce_date(
                            getattr(pos, "next_reprice_date"),
                            field_name="next_reprice_date", row_id=cid,
                        )
                    frequency = None
                    if "repricing_freq" in nii_positions.columns:
                        frequency = parse_frequency_token(
                            getattr(pos, "repricing_freq", None), row_id=cid,
                        )
                    pre_nii = project_variable_bullet_cycle(
                        cycle_start=accrual_start, cycle_end=accrual_end,
                        notional=notional, sign=sign, base=base,
                        index_name=index_name, spread=spread,
                        floor_rate=floor_rate, cap_rate=cap_rate,
                        curve_set=curve_set, anchor_date=anchor_date,
                        frequency=frequency, fixed_rate_for_stub=fixed_rate_stub,
                    )
                else:
                    fixed_rate = coerce_float(
                        getattr(pos, "fixed_rate"), field_name="fixed_rate", row_id=cid,
                    )
                    pre_nii = sign * notional * fixed_rate * yearfrac(
                        accrual_start, accrual_end, base
                    )

                if abs(pre_nii) > 1e-16:
                    _prorate_to_months(
                        pre_nii, accrual_start, accrual_end,
                        analysis_date, horizon_months, is_asset, monthly,
                        month_bounds,
                    )
                    if is_asset:
                        total_income += pre_nii
                    else:
                        total_expense += pre_nii

                # Renewal
                renewal_nii = _compute_renewal_nii(
                    pos, cid, sct, curve_set, analysis_date, horizon_end,
                    horizon_months, notional, sign, base, is_asset,
                    margin_set, risk_free_index, nii_positions,
                    scheduled_principal_flows, monthly,
                    month_bounds, rate_cache,
                )
                if is_asset:
                    total_income += renewal_nii
                else:
                    total_expense += renewal_nii

    aggregate = total_income + total_expense

    return NiiFromCashflowsResult(
        aggregate_nii=float(aggregate),
        asset_nii=float(total_income),
        liability_nii=float(total_expense),
        monthly_breakdown=_monthly_to_list(monthly, horizon_months),
    )
