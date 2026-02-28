from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

import pandas as pd

from engine.config.eve_buckets import DEFAULT_REGULATORY_BUCKETS
from engine.core.daycount import normalize_daycount_base, yearfrac
from engine.services._eve_utils import EVEBucket, normalise_buckets as _normalise_buckets_shared
from engine.services.market import ForwardCurveSet
from engine.services.nii_projectors import (
    FIXED_ANNUITY_REQUIRED_COLUMNS,
    FIXED_BULLET_REQUIRED_COLUMNS,
    FIXED_LINEAR_REQUIRED_COLUMNS,
    FIXED_SCHEDULED_REQUIRED_COLUMNS,
    VARIABLE_ANNUITY_REQUIRED_COLUMNS,
    VARIABLE_BULLET_REQUIRED_COLUMNS,
    VARIABLE_LINEAR_REQUIRED_COLUMNS,
    VARIABLE_SCHEDULED_REQUIRED_COLUMNS,
    add_frequency,
    annuity_payment_amount,
    apply_floor_cap,
    apply_principal_flow,
    build_payment_dates,
    build_reset_dates,
    coerce_date,
    coerce_float,
    ensure_required_columns,
    first_reset_after_accrual_start,
    is_blank,
    linear_notional_at,
    parse_frequency_token,
    payment_frequency_or_default,
    prepare_scheduled_principal_flows,
    reset_occurs_on_accrual_start,
    scheduled_flow_map_for_window,
    side_sign,
)


@dataclass
class EVERunResult:
    analysis_date: Any
    method: str
    base_eve: float
    scenario_eve: dict[str, float]


_IMPLEMENTED_SOURCE_CONTRACT_TYPES = {
    "fixed_annuity",
    "fixed_bullet",
    "fixed_linear",
    "fixed_scheduled",
    "variable_annuity",
    "variable_bullet",
    "variable_linear",
    "variable_scheduled",
    "variable_non_maturity",
}
_EXCLUDED_SOURCE_CONTRACT_TYPES = {
    "static_position",
    "fixed_non_maturity",
}

# Synthetic maturity for variable NMDs (30 years from analysis_date).
# EVE sensitivity is driven by time to next repricing, not maturity.
_VARIABLE_NMD_SYNTHETIC_MATURITY_YEARS = 30

_DEFAULT_BULLET_PAYMENT_FREQUENCY = (1, "Y")


def _normalise_source_contract_type(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip().str.lower()


def _normalise_rate_type(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip().str.lower()


def _frequency_from_row_with_default(
    row,
    *,
    row_id: object,
    default: tuple[int, str],
) -> tuple[int, str]:
    freq = parse_frequency_token(getattr(row, "payment_freq", None), row_id=row_id, field_name="payment_freq")
    if freq is None:
        freq = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id, field_name="repricing_freq")
    return default if freq is None else freq


def _build_coupon_dates(
    *,
    start_date: date,
    maturity_date: date,
    payment_frequency: tuple[int, str],
) -> list[date]:
    if maturity_date <= start_date:
        return []

    out: list[date] = []
    d = add_frequency(start_date, payment_frequency)
    guard = 0
    while d < maturity_date:
        out.append(d)
        d_next = add_frequency(d, payment_frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Unexpected loop while generating EVE coupon dates.")
    out.append(maturity_date)
    return out


def _add_flow(
    flow_map: dict[date, dict[str, float]],
    *,
    flow_date: date,
    interest_amount: float = 0.0,
    principal_amount: float = 0.0,
) -> None:
    if flow_date not in flow_map:
        flow_map[flow_date] = {"interest_amount": 0.0, "principal_amount": 0.0}
    flow_map[flow_date]["interest_amount"] += float(interest_amount)
    flow_map[flow_date]["principal_amount"] += float(principal_amount)


def _append_contract_records(
    records: list[dict[str, Any]],
    *,
    flow_map: dict[date, dict[str, float]],
    contract_id: str,
    source_contract_type: str,
    rate_type: str,
    side: str,
    index_name: str | None,
) -> None:
    for flow_date in sorted(flow_map.keys()):
        interest_amount = float(flow_map[flow_date].get("interest_amount", 0.0))
        principal_amount = float(flow_map[flow_date].get("principal_amount", 0.0))
        total_amount = float(interest_amount + principal_amount)
        if abs(total_amount) <= 1e-16:
            continue

        records.append(
            {
                "contract_id": contract_id,
                "source_contract_type": source_contract_type,
                "rate_type": rate_type,
                "side": side,
                "index_name": index_name,
                "flow_date": flow_date,
                "interest_amount": interest_amount,
                "principal_amount": principal_amount,
                "total_amount": total_amount,
            }
        )


def _daycount_base_days(convention: str) -> float:
    """Extract the numeric base (360 or 365) from a daycount convention string."""
    c = str(convention).strip().upper()
    if "365" in c:
        return 365.0
    return 360.0  # 30/360, ACT/360 → 360


def _apply_cpr_overlay(
    flow_map: dict[date, dict[str, float]],
    *,
    outstanding: float,
    sign: float,
    cpr_annual: float,
    daycount_base_days: float,
    accrual_start: date | None = None,
) -> dict[date, dict[str, float]]:
    """Apply CPR/TDRR dual-schedule overlay to a contractual flow_map.

    Reads the signed contractual flows, computes behavioural (prepaid)
    flows using the Banca Etica validated formula:
        QCm(t) = DRm(t) * min(1, QCc(t)/DRc(t) + CPRp(t))
        QIp(t) = QIc(t) * DRm(t) / DRc(t)
    Returns a new flow_map with behavioural values.
    """
    if cpr_annual <= 0.0:
        return flow_map

    sorted_dates = sorted(flow_map.keys())
    if not sorted_dates:
        return flow_map

    behavioural: dict[date, dict[str, float]] = {}
    DRc = float(outstanding)
    DRm = float(outstanding)
    # For the first period, use accrual_start if provided so the first
    # flow gets a non-zero CPRp (matching Banca Etica validation).
    prev_date = accrual_start if accrual_start is not None else sorted_dates[0]

    for flow_date in sorted_dates:
        vals = flow_map[flow_date]
        QIc = abs(float(vals.get("interest_amount", 0.0)))
        QCc = abs(float(vals.get("principal_amount", 0.0)))

        # Periodic CPR from days since previous flow (or accrual_start)
        days = (flow_date - prev_date).days
        CPRp = 1.0 - (1.0 - cpr_annual) ** (days / daycount_base_days) if days > 0 else 0.0

        # Contractual amortization rate
        amort_rate = QCc / DRc if DRc > 1e-10 else 1.0

        # Behavioural principal and interest
        combined = min(1.0, amort_rate + CPRp)
        QCm = DRm * combined
        QIp = QIc * (DRm / DRc) if DRc > 1e-10 else 0.0

        behavioural[flow_date] = {
            "interest_amount": sign * QIp,
            "principal_amount": sign * QCm,
        }

        DRm = max(0.0, DRm - QCm)
        DRc = max(0.0, DRc - QCc)
        prev_date = flow_date

    return behavioural


def _positions_by_supported_type(positions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if positions.empty:
        return {}

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
                "EVE supports source_contract_type in "
                "['fixed_annuity', 'fixed_bullet', 'fixed_linear', 'fixed_scheduled', "
                "'variable_annuity', 'variable_bullet', 'variable_linear', 'variable_scheduled']. "
                f"Unimplemented types found: {unknown}"
            )

        out: dict[str, pd.DataFrame] = {}
        for contract_type in sorted(_IMPLEMENTED_SOURCE_CONTRACT_TYPES):
            if contract_type == "variable_non_maturity":
                continue  # handled below — routed to variable_bullet
            mask = sct.eq(contract_type)
            if mask.any():
                out[contract_type] = positions.loc[mask].copy()

        # Route variable_non_maturity → variable_bullet with synthetic maturity
        vnm_mask = sct.eq("variable_non_maturity")
        if vnm_mask.any():
            vnm_df = positions.loc[vnm_mask].copy()
            # Synthetic maturity 30Y from today — far enough that EVE sensitivity
            # is driven by repricing frequency, not maturity.
            synthetic_mat = date.today().replace(
                year=date.today().year + _VARIABLE_NMD_SYNTHETIC_MATURITY_YEARS
            )
            vnm_df["maturity_date"] = synthetic_mat
            vnm_df["source_contract_type"] = "variable_bullet"
            if "variable_bullet" in out:
                out["variable_bullet"] = pd.concat(
                    [out["variable_bullet"], vnm_df], ignore_index=True
                )
            else:
                out["variable_bullet"] = vnm_df

        return out

    if "rate_type" not in positions.columns or "maturity_date" not in positions.columns:
        raise ValueError(
            "positions does not contain 'source_contract_type' or fallback columns "
            "('rate_type', 'maturity_date')."
        )

    out: dict[str, pd.DataFrame] = {}
    rt = _normalise_rate_type(positions["rate_type"])
    fixed_mask = rt.eq("fixed") & positions["maturity_date"].notna()
    float_mask = rt.eq("float") & positions["maturity_date"].notna()

    if fixed_mask.any():
        p = positions.loc[fixed_mask].copy()
        p["source_contract_type"] = "fixed_bullet"
        out["fixed_bullet"] = p

    if float_mask.any():
        p = positions.loc[float_mask].copy()
        p["source_contract_type"] = "variable_bullet"
        out["variable_bullet"] = p

    return out


def _extend_fixed_bullet_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, FIXED_BULLET_REQUIRED_COLUMNS, "fixed_bullet")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in FIXED_BULLET_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        notional = coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        payment_frequency = _frequency_from_row_with_default(
            row,
            row_id=row_id,
            default=_DEFAULT_BULLET_PAYMENT_FREQUENCY,
        )

        flow_map: dict[date, dict[str, float]] = {}
        coupon_dates = _build_coupon_dates(
            start_date=start_date,
            maturity_date=maturity_date,
            payment_frequency=payment_frequency,
        )
        prev = start_date
        for pay_date in coupon_dates:
            if pay_date <= prev:
                continue
            if pay_date <= analysis_date:
                prev = pay_date
                continue

            accrual_start = max(prev, analysis_date)
            if pay_date > accrual_start:
                interest = sign * notional * fixed_rate * yearfrac(accrual_start, pay_date, base)
                _add_flow(flow_map, flow_date=pay_date, interest_amount=interest)
            prev = pay_date

        _add_flow(flow_map, flow_date=maturity_date, principal_amount=sign * notional)
        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=notional, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="fixed_bullet",
            rate_type="fixed",
            side=str(row.side).strip(),
            index_name=None,
        )


def _extend_fixed_linear_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, FIXED_LINEAR_REQUIRED_COLUMNS, "fixed_linear")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in FIXED_LINEAR_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        outstanding = coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        cycle_start = max(start_date, analysis_date)
        if maturity_date <= cycle_start:
            continue

        payment_frequency = payment_frequency_or_default(row, row_id=row_id)
        payment_dates = build_payment_dates(
            cycle_start=cycle_start,
            cycle_maturity=maturity_date,
            payment_frequency=payment_frequency,
        )
        if not payment_dates:
            continue

        flow_map: dict[date, dict[str, float]] = {}
        prev = cycle_start
        for pay_date in payment_dates:
            if pay_date <= prev:
                continue

            n_start = linear_notional_at(
                prev,
                effective_start=cycle_start,
                maturity_date=maturity_date,
                outstanding_at_effective_start=outstanding,
            )
            n_end = linear_notional_at(
                pay_date,
                effective_start=cycle_start,
                maturity_date=maturity_date,
                outstanding_at_effective_start=outstanding,
            )
            avg_notional = 0.5 * (n_start + n_end)
            interest = sign * avg_notional * fixed_rate * yearfrac(prev, pay_date, base)
            principal = sign * max(0.0, n_start - n_end)
            _add_flow(
                flow_map,
                flow_date=pay_date,
                interest_amount=interest,
                principal_amount=principal,
            )
            prev = pay_date

        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=outstanding, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="fixed_linear",
            rate_type="fixed",
            side=str(row.side).strip(),
            index_name=None,
        )


def _extend_fixed_annuity_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, FIXED_ANNUITY_REQUIRED_COLUMNS, "fixed_annuity")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in FIXED_ANNUITY_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        outstanding = coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        cycle_start = max(start_date, analysis_date)
        if maturity_date <= cycle_start:
            continue

        payment_frequency = payment_frequency_or_default(row, row_id=row_id)
        payment_dates = build_payment_dates(
            cycle_start=cycle_start,
            cycle_maturity=maturity_date,
            payment_frequency=payment_frequency,
        )
        if not payment_dates:
            continue

        payment = annuity_payment_amount(
            outstanding=outstanding,
            rate=fixed_rate,
            period_start=cycle_start,
            payment_dates=payment_dates,
            base=base,
        )

        flow_map: dict[date, dict[str, float]] = {}
        balance = float(outstanding)
        prev = cycle_start
        for i, pay_date in enumerate(payment_dates):
            if pay_date <= prev or balance <= 1e-10:
                continue

            interest = balance * fixed_rate * yearfrac(prev, pay_date, base)
            is_last_payment = i == (len(payment_dates) - 1)
            if is_last_payment:
                principal = balance
            else:
                principal = payment - interest
                principal = max(0.0, min(principal, balance))

            _add_flow(
                flow_map,
                flow_date=pay_date,
                interest_amount=sign * interest,
                principal_amount=sign * principal,
            )
            balance = max(0.0, balance - principal)
            prev = pay_date

        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=outstanding, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="fixed_annuity",
            rate_type="fixed",
            side=str(row.side).strip(),
            index_name=None,
        )


def _extend_variable_bullet_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    projection_curve_set: ForwardCurveSet,
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, VARIABLE_BULLET_REQUIRED_COLUMNS, "variable_bullet")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in VARIABLE_BULLET_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        notional = coerce_float(row.notional, field_name="notional", row_id=row_id)
        spread = coerce_float(row.spread, field_name="spread", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        index_name = str(row.index_name).strip()
        projection_curve_set.get(index_name)

        cycle_start = max(start_date, analysis_date)
        payment_frequency = _frequency_from_row_with_default(
            row,
            row_id=row_id,
            default=_DEFAULT_BULLET_PAYMENT_FREQUENCY,
        )

        anchor_date = None
        if "next_reprice_date" in positions.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        repricing_frequency = None
        if "repricing_freq" in positions.columns:
            repricing_frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)
        fixed_rate_stub = None
        if not is_blank(getattr(row, "fixed_rate", None)):
            fixed_rate_stub = coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)

        first_reset_after = first_reset_after_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_at_start = reset_occurs_on_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_dates = build_reset_dates(
            accrual_start=cycle_start,
            accrual_end=maturity_date,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )

        flow_map: dict[date, dict[str, float]] = {}
        period_start = start_date
        for pay_date in _build_coupon_dates(
            start_date=start_date,
            maturity_date=maturity_date,
            payment_frequency=payment_frequency,
        ):
            if pay_date <= analysis_date:
                period_start = pay_date
                continue

            accrual_start = max(period_start, analysis_date)
            if pay_date <= accrual_start:
                period_start = pay_date
                continue

            segment_points = [accrual_start, pay_date]
            for d in reset_dates:
                if accrual_start < d < pay_date:
                    segment_points.append(d)
            segment_points = sorted(set(segment_points))

            period_interest = 0.0
            for i in range(len(segment_points) - 1):
                seg_start = segment_points[i]
                seg_end = segment_points[i + 1]
                if seg_end <= seg_start:
                    continue

                use_current_coupon = (
                    (fixed_rate_stub is not None)
                    and (not reset_at_start)
                    and (first_reset_after is not None)
                    and (seg_start < first_reset_after)
                )
                if use_current_coupon:
                    seg_rate = float(fixed_rate_stub)
                else:
                    seg_rate = float(projection_curve_set.rate_on_date(index_name, seg_start)) + float(spread)
                seg_rate = apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)
                period_interest += sign * notional * seg_rate * yearfrac(seg_start, seg_end, base)

            _add_flow(flow_map, flow_date=pay_date, interest_amount=period_interest)
            period_start = pay_date

        _add_flow(flow_map, flow_date=maturity_date, principal_amount=sign * notional)
        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=notional, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="variable_bullet",
            rate_type="float",
            side=str(row.side).strip(),
            index_name=index_name,
        )


def _extend_variable_linear_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    projection_curve_set: ForwardCurveSet,
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, VARIABLE_LINEAR_REQUIRED_COLUMNS, "variable_linear")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in VARIABLE_LINEAR_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        outstanding = coerce_float(row.notional, field_name="notional", row_id=row_id)
        spread = coerce_float(row.spread, field_name="spread", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        index_name = str(row.index_name).strip()
        projection_curve_set.get(index_name)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)

        cycle_start = max(start_date, analysis_date)
        if maturity_date <= cycle_start:
            continue

        payment_frequency = payment_frequency_or_default(row, row_id=row_id)
        payment_dates = build_payment_dates(
            cycle_start=cycle_start,
            cycle_maturity=maturity_date,
            payment_frequency=payment_frequency,
        )
        if not payment_dates:
            continue

        anchor_date = None
        if "next_reprice_date" in positions.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        repricing_frequency = None
        if "repricing_freq" in positions.columns:
            repricing_frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)
        fixed_rate_stub = None
        if not is_blank(getattr(row, "fixed_rate", None)):
            fixed_rate_stub = coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)

        first_reset_after = first_reset_after_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_at_start = reset_occurs_on_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_dates = build_reset_dates(
            accrual_start=cycle_start,
            accrual_end=maturity_date,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )

        flow_map: dict[date, dict[str, float]] = {}
        prev = cycle_start
        for pay_date in payment_dates:
            if pay_date <= prev:
                continue

            period_points = [prev, pay_date]
            for d in reset_dates:
                if prev < d < pay_date:
                    period_points.append(d)
            period_points = sorted(set(period_points))

            period_interest = 0.0
            for i in range(len(period_points) - 1):
                seg_start = period_points[i]
                seg_end = period_points[i + 1]
                if seg_end <= seg_start:
                    continue

                use_current_coupon = (
                    (fixed_rate_stub is not None)
                    and (not reset_at_start)
                    and (first_reset_after is not None)
                    and (seg_start < first_reset_after)
                )
                if use_current_coupon:
                    seg_rate = float(fixed_rate_stub)
                else:
                    seg_rate = float(projection_curve_set.rate_on_date(index_name, seg_start)) + float(spread)
                seg_rate = apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)

                n_start = linear_notional_at(
                    seg_start,
                    effective_start=cycle_start,
                    maturity_date=maturity_date,
                    outstanding_at_effective_start=outstanding,
                )
                n_end = linear_notional_at(
                    seg_end,
                    effective_start=cycle_start,
                    maturity_date=maturity_date,
                    outstanding_at_effective_start=outstanding,
                )
                avg_notional = 0.5 * (n_start + n_end)
                period_interest += sign * avg_notional * seg_rate * yearfrac(seg_start, seg_end, base)

            n_period_start = linear_notional_at(
                prev,
                effective_start=cycle_start,
                maturity_date=maturity_date,
                outstanding_at_effective_start=outstanding,
            )
            n_period_end = linear_notional_at(
                pay_date,
                effective_start=cycle_start,
                maturity_date=maturity_date,
                outstanding_at_effective_start=outstanding,
            )
            period_principal = sign * max(0.0, n_period_start - n_period_end)

            _add_flow(
                flow_map,
                flow_date=pay_date,
                interest_amount=period_interest,
                principal_amount=period_principal,
            )
            prev = pay_date

        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=outstanding, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="variable_linear",
            rate_type="float",
            side=str(row.side).strip(),
            index_name=index_name,
        )


def _extend_variable_annuity_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    projection_curve_set: ForwardCurveSet,
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, VARIABLE_ANNUITY_REQUIRED_COLUMNS, "variable_annuity")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in VARIABLE_ANNUITY_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        outstanding = coerce_float(row.notional, field_name="notional", row_id=row_id)
        spread = coerce_float(row.spread, field_name="spread", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        index_name = str(row.index_name).strip()
        projection_curve_set.get(index_name)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)

        cycle_start = max(start_date, analysis_date)
        if maturity_date <= cycle_start:
            continue

        payment_frequency = payment_frequency_or_default(row, row_id=row_id)
        payment_dates = build_payment_dates(
            cycle_start=cycle_start,
            cycle_maturity=maturity_date,
            payment_frequency=payment_frequency,
        )
        if not payment_dates:
            continue

        anchor_date = None
        if "next_reprice_date" in positions.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        repricing_frequency = None
        if "repricing_freq" in positions.columns:
            repricing_frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)
        fixed_rate_stub = None
        if not is_blank(getattr(row, "fixed_rate", None)):
            fixed_rate_stub = coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)

        first_reset_after = first_reset_after_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_at_start = reset_occurs_on_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_dates = build_reset_dates(
            accrual_start=cycle_start,
            accrual_end=maturity_date,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        regime_bounds = [cycle_start, *reset_dates, maturity_date]

        flow_map: dict[date, dict[str, float]] = {}
        balance = float(outstanding)
        for ridx in range(len(regime_bounds) - 1):
            regime_start = regime_bounds[ridx]
            regime_end = regime_bounds[ridx + 1]
            if regime_end <= regime_start or balance <= 1e-10:
                continue

            use_current_coupon = (
                (fixed_rate_stub is not None)
                and (not reset_at_start)
                and (first_reset_after is not None)
                and (regime_start < first_reset_after)
            )
            if use_current_coupon:
                regime_rate = float(fixed_rate_stub)
            else:
                regime_rate = float(projection_curve_set.rate_on_date(index_name, regime_start)) + float(spread)
            regime_rate = apply_floor_cap(regime_rate, floor_rate=floor_rate, cap_rate=cap_rate)

            remaining_payment_dates = [d for d in payment_dates if d > regime_start]
            if not remaining_payment_dates:
                break
            payment = annuity_payment_amount(
                outstanding=balance,
                rate=regime_rate,
                period_start=regime_start,
                payment_dates=remaining_payment_dates,
                base=base,
            )

            prev = regime_start
            payment_dates_regime = [d for d in payment_dates if d > regime_start and d <= regime_end]
            for pay_date in payment_dates_regime:
                if pay_date <= prev or balance <= 1e-10:
                    continue
                interest = balance * regime_rate * yearfrac(prev, pay_date, base)
                is_last_payment = pay_date == payment_dates[-1]
                if is_last_payment:
                    principal = balance
                else:
                    principal = payment - interest
                    principal = max(0.0, min(principal, balance))

                _add_flow(
                    flow_map,
                    flow_date=pay_date,
                    interest_amount=sign * interest,
                    principal_amount=sign * principal,
                )
                balance = max(0.0, balance - principal)
                prev = pay_date

            # If the reset falls between coupons, accrue the stub to the end of the regime.
            if balance > 1e-10 and regime_end > prev:
                stub_interest = balance * regime_rate * yearfrac(prev, regime_end, base)
                _add_flow(flow_map, flow_date=regime_end, interest_amount=sign * stub_interest)

        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=outstanding, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="variable_annuity",
            rate_type="float",
            side=str(row.side).strip(),
            index_name=index_name,
        )


def _extend_fixed_scheduled_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    flows_by_contract: dict[str, list[tuple[date, float]]],
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, FIXED_SCHEDULED_REQUIRED_COLUMNS, "fixed_scheduled")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in FIXED_SCHEDULED_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        outstanding = coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        cycle_start = max(start_date, analysis_date)
        if maturity_date <= cycle_start:
            continue

        contract_flows = flows_by_contract.get(contract_id, [])
        flow_map_sched = scheduled_flow_map_for_window(
            contract_flows,
            cycle_start=cycle_start,
            cycle_end=maturity_date,
        )
        boundaries = {cycle_start, maturity_date}
        for d in flow_map_sched.keys():
            if cycle_start < d <= maturity_date:
                boundaries.add(d)
        ordered = sorted(boundaries)

        flow_map: dict[date, dict[str, float]] = {}
        balance = float(outstanding)
        for i in range(len(ordered) - 1):
            seg_start = ordered[i]
            seg_end = ordered[i + 1]
            if seg_end <= seg_start or balance <= 1e-10:
                continue

            interest = sign * balance * fixed_rate * yearfrac(seg_start, seg_end, base)
            principal_raw = float(flow_map_sched.get(seg_end, 0.0))
            principal = sign * principal_raw
            _add_flow(
                flow_map,
                flow_date=seg_end,
                interest_amount=interest,
                principal_amount=principal,
            )
            balance = apply_principal_flow(balance, principal_raw)

        if balance > 1e-10:
            _add_flow(flow_map, flow_date=maturity_date, principal_amount=sign * balance)

        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=outstanding, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="fixed_scheduled",
            rate_type="fixed",
            side=str(row.side).strip(),
            index_name=None,
        )


def _extend_variable_scheduled_cashflows(
    records: list[dict[str, Any]],
    *,
    positions: pd.DataFrame,
    analysis_date: date,
    projection_curve_set: ForwardCurveSet,
    flows_by_contract: dict[str, list[tuple[date, float]]],
    cpr_annual: float = 0.0,
) -> None:
    if positions.empty:
        return
    ensure_required_columns(positions, VARIABLE_SCHEDULED_REQUIRED_COLUMNS, "variable_scheduled")

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in VARIABLE_SCHEDULED_REQUIRED_COLUMNS:
            if is_blank(getattr(row, col, None)):
                raise ValueError(f"Required value is empty in {col!r} for contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        start_date = coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date <= analysis_date:
            continue
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date for contract_id={row_id!r}")

        outstanding = coerce_float(row.notional, field_name="notional", row_id=row_id)
        spread = coerce_float(row.spread, field_name="spread", row_id=row_id)
        base = normalize_daycount_base(str(row.daycount_base))
        sign = side_sign(row.side, row_id=row_id)
        index_name = str(row.index_name).strip()
        projection_curve_set.get(index_name)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)

        cycle_start = max(start_date, analysis_date)
        if maturity_date <= cycle_start:
            continue

        anchor_date = None
        if "next_reprice_date" in positions.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        repricing_frequency = None
        if "repricing_freq" in positions.columns:
            repricing_frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)
        fixed_rate_stub = None
        if not is_blank(getattr(row, "fixed_rate", None)):
            fixed_rate_stub = coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)

        first_reset_after = first_reset_after_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_at_start = reset_occurs_on_accrual_start(
            accrual_start=cycle_start,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )
        reset_dates = build_reset_dates(
            accrual_start=cycle_start,
            accrual_end=maturity_date,
            anchor_date=anchor_date,
            frequency=repricing_frequency,
        )

        contract_flows = flows_by_contract.get(contract_id, [])
        flow_map_sched = scheduled_flow_map_for_window(
            contract_flows,
            cycle_start=cycle_start,
            cycle_end=maturity_date,
        )

        boundaries = {cycle_start, maturity_date}
        for d in reset_dates:
            if cycle_start < d < maturity_date:
                boundaries.add(d)
        for d in flow_map_sched.keys():
            if cycle_start < d <= maturity_date:
                boundaries.add(d)
        ordered = sorted(boundaries)

        flow_map: dict[date, dict[str, float]] = {}
        balance = float(outstanding)
        for i in range(len(ordered) - 1):
            seg_start = ordered[i]
            seg_end = ordered[i + 1]
            if seg_end <= seg_start or balance <= 1e-10:
                continue

            use_current_coupon = (
                (fixed_rate_stub is not None)
                and (not reset_at_start)
                and (first_reset_after is not None)
                and (seg_start < first_reset_after)
            )
            if use_current_coupon:
                seg_rate = float(fixed_rate_stub)
            else:
                seg_rate = float(projection_curve_set.rate_on_date(index_name, seg_start)) + float(spread)
            seg_rate = apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)

            interest = sign * balance * seg_rate * yearfrac(seg_start, seg_end, base)
            principal_raw = float(flow_map_sched.get(seg_end, 0.0))
            principal = sign * principal_raw
            _add_flow(
                flow_map,
                flow_date=seg_end,
                interest_amount=interest,
                principal_amount=principal,
            )
            balance = apply_principal_flow(balance, principal_raw)

        if balance > 1e-10:
            _add_flow(flow_map, flow_date=maturity_date, principal_amount=sign * balance)

        if cpr_annual > 0.0:
            flow_map = _apply_cpr_overlay(
                flow_map, outstanding=outstanding, sign=sign,
                cpr_annual=cpr_annual, daycount_base_days=_daycount_base_days(base),
                accrual_start=analysis_date,
            )
        _append_contract_records(
            records,
            flow_map=flow_map,
            contract_id=contract_id,
            source_contract_type="variable_scheduled",
            rate_type="float",
            side=str(row.side).strip(),
            index_name=index_name,
        )


def build_eve_cashflows(
    positions: pd.DataFrame,
    *,
    analysis_date: date,
    projection_curve_set: ForwardCurveSet | None = None,
    scheduled_principal_flows: pd.DataFrame | None = None,
    nmd_params=None,
    cpr_annual: float = 0.0,
    tdrr_annual: float = 0.0,
) -> pd.DataFrame:
    """
    Builds run-off cashflows for EVE.

    Amounts are signed:
    - asset -> positive
    - liability -> negative
    """
    groups = _positions_by_supported_type(positions)
    if not groups:
        return pd.DataFrame(
            columns=[
                "contract_id",
                "source_contract_type",
                "rate_type",
                "side",
                "index_name",
                "flow_date",
                "interest_amount",
                "principal_amount",
                "total_amount",
            ]
        )

    variable_present = any(k.startswith("variable_") for k in groups.keys())
    if variable_present and projection_curve_set is None:
        raise ValueError("projection_curve_set is required for variable instruments in EVE.")

    has_scheduled = ("fixed_scheduled" in groups) or ("variable_scheduled" in groups)
    flows_by_contract: dict[str, list[tuple[date, float]]] = {}
    if has_scheduled:
        if scheduled_principal_flows is None:
            raise ValueError(
                "Scheduled positions received but scheduled_principal_flows is missing."
            )
        flows_by_contract = prepare_scheduled_principal_flows(scheduled_principal_flows)

    records: list[dict[str, Any]] = []

    # ── Helper: determine effective decay rate per position sub-group ──
    # CPR applies to asset-side loans; TDRR applies to term-deposit liabilities.
    def _effective_decay(pos_df: pd.DataFrame) -> float:
        """Return the single decay rate for a homogeneous sub-group.

        For mixed asset/liability groups, we call the generator twice
        (split by side), each with the correct rate.
        """
        if pos_df.empty:
            return 0.0
        if cpr_annual > 0.0 or tdrr_annual > 0.0:
            sides = pos_df["side"].str.strip().str.upper().unique() if "side" in pos_df.columns else []
            has_asset = "A" in sides
            has_liab = "L" in sides
            if has_asset and not has_liab:
                return cpr_annual
            if has_liab and not has_asset:
                # TDRR only for term deposits; if is_term_deposit column
                # exists, filter was already applied upstream
                if tdrr_annual > 0.0 and "is_term_deposit" in pos_df.columns:
                    if pos_df["is_term_deposit"].any():
                        return tdrr_annual
                return 0.0
        return 0.0

    def _split_and_extend(extend_fn, sct_key, **extra_kw):
        """Call an _extend_*_cashflows function, splitting by CPR/TDRR as needed."""
        pos_df = groups.get(sct_key, pd.DataFrame())
        if pos_df.empty:
            return
        has_side = "side" in pos_df.columns
        needs_split = (cpr_annual > 0.0 or tdrr_annual > 0.0) and has_side

        if not needs_split:
            extend_fn(records, positions=pos_df, analysis_date=analysis_date,
                       cpr_annual=0.0, **extra_kw)
            return

        side_col = pos_df["side"].str.strip().str.upper()
        asset_mask = side_col.eq("A")
        liab_mask = ~asset_mask

        # Assets get CPR
        asset_df = pos_df.loc[asset_mask]
        if not asset_df.empty:
            extend_fn(records, positions=asset_df, analysis_date=analysis_date,
                       cpr_annual=cpr_annual, **extra_kw)

        # Liabilities: term deposits get TDRR, others get no decay
        liab_df = pos_df.loc[liab_mask]
        if not liab_df.empty and tdrr_annual > 0.0:
            if "is_term_deposit" in liab_df.columns:
                td_col = liab_df["is_term_deposit"]
                td_mask = td_col.notna() & td_col.astype(bool)
                td_df = liab_df.loc[td_mask]
                non_td_df = liab_df.loc[~td_mask]
                if not td_df.empty:
                    extend_fn(records, positions=td_df, analysis_date=analysis_date,
                               cpr_annual=tdrr_annual, **extra_kw)
                if not non_td_df.empty:
                    extend_fn(records, positions=non_td_df, analysis_date=analysis_date,
                               cpr_annual=0.0, **extra_kw)
            else:
                extend_fn(records, positions=liab_df, analysis_date=analysis_date,
                           cpr_annual=0.0, **extra_kw)
        elif not liab_df.empty:
            extend_fn(records, positions=liab_df, analysis_date=analysis_date,
                       cpr_annual=0.0, **extra_kw)

    _split_and_extend(_extend_fixed_annuity_cashflows, "fixed_annuity")
    _split_and_extend(_extend_fixed_bullet_cashflows, "fixed_bullet")
    _split_and_extend(_extend_fixed_linear_cashflows, "fixed_linear")
    _split_and_extend(_extend_fixed_scheduled_cashflows, "fixed_scheduled",
                      flows_by_contract=flows_by_contract)

    if projection_curve_set is not None:
        _split_and_extend(_extend_variable_annuity_cashflows, "variable_annuity",
                          projection_curve_set=projection_curve_set)
        _split_and_extend(_extend_variable_bullet_cashflows, "variable_bullet",
                          projection_curve_set=projection_curve_set)
        _split_and_extend(_extend_variable_linear_cashflows, "variable_linear",
                          projection_curve_set=projection_curve_set)
        _split_and_extend(_extend_variable_scheduled_cashflows, "variable_scheduled",
                          projection_curve_set=projection_curve_set,
                          flows_by_contract=flows_by_contract)

    # ── NMD behavioural expansion (Phase 3) ─────────────────────────────
    if nmd_params is not None and "source_contract_type" in positions.columns:
        sct_col = _normalise_source_contract_type(positions["source_contract_type"])
        nmd_mask = sct_col.eq("fixed_non_maturity")
        nmd_df = positions.loc[nmd_mask]
        if not nmd_df.empty:
            from engine.services.nmd_behavioural import expand_nmd_positions
            nmd_cf = expand_nmd_positions(nmd_df, nmd_params, analysis_date)
            if not nmd_cf.empty:
                records.extend(nmd_cf.to_dict("records"))

    out = pd.DataFrame(records)
    if out.empty:
        return pd.DataFrame(
            columns=[
                "contract_id",
                "source_contract_type",
                "rate_type",
                "side",
                "index_name",
                "flow_date",
                "interest_amount",
                "principal_amount",
                "total_amount",
            ]
        )

    out["flow_date"] = pd.to_datetime(out["flow_date"], errors="coerce").dt.date
    out = out.sort_values(
        ["flow_date", "source_contract_type", "contract_id"],
        kind="stable",
    ).reset_index(drop=True)
    return out


def _cashflow_yearfrac(
    *,
    analysis_date: date,
    flow_date: date,
    base: str,
) -> float:
    return max(0.0, float(yearfrac(analysis_date, flow_date, base)))


def evaluate_eve_exact(
    cashflows: pd.DataFrame,
    *,
    discount_curve_set: ForwardCurveSet,
    discount_index: str = "EUR_ESTR_OIS",
) -> float:
    if cashflows.empty:
        return 0.0

    discount_curve_set.get(discount_index)
    pv = 0.0
    for row in cashflows.itertuples(index=False):
        flow_date = coerce_date(row.flow_date, field_name="flow_date", row_id=getattr(row, "contract_id", None))
        amount = float(row.total_amount)
        df = float(discount_curve_set.df_on_date(discount_index, flow_date))
        pv += amount * df
    return float(pv)


def _normalise_buckets(
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None,
) -> list[EVEBucket]:
    return _normalise_buckets_shared(buckets, default=DEFAULT_REGULATORY_BUCKETS)


def build_bucketed_cashflow_table(
    cashflows: pd.DataFrame,
    *,
    discount_curve_set: ForwardCurveSet,
    discount_index: str = "EUR_ESTR_OIS",
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
    open_ended_bucket_years: float = 10.0,
) -> pd.DataFrame:
    norm_buckets = _normalise_buckets(buckets)
    discount_curve = discount_curve_set.get(discount_index)
    base = normalize_daycount_base(discount_curve_set.base)

    if cashflows.empty:
        return pd.DataFrame(
            columns=[
                "bucket_name",
                "bucket_start_years",
                "bucket_end_years",
                "representative_t",
                "discount_factor",
                "net_cashflow",
                "pv_amount",
            ]
        )

    flow_work = cashflows.copy()
    flow_work["flow_date"] = pd.to_datetime(flow_work["flow_date"], errors="coerce").dt.date
    if flow_work["flow_date"].isna().any():
        rows = [int(i) + 2 for i in flow_work.index[flow_work["flow_date"].isna()][:10].tolist()]
        raise ValueError(f"Cashflows with invalid flow_date in rows {rows}")

    flow_work["t_years"] = flow_work["flow_date"].apply(
        lambda d: _cashflow_yearfrac(
            analysis_date=discount_curve_set.analysis_date,
            flow_date=d,
            base=base,
        )
    )

    def _assign_bucket_name(t: float) -> str:
        for bucket in norm_buckets:
            if bucket.contains(t):
                return bucket.name
        return norm_buckets[-1].name

    flow_work["bucket_name"] = flow_work["t_years"].astype(float).apply(_assign_bucket_name)
    grouped = (
        flow_work.groupby("bucket_name", as_index=False)["total_amount"]
        .sum()
        .rename(columns={"total_amount": "net_cashflow"})
    )
    net_by_bucket = dict(zip(grouped["bucket_name"], grouped["net_cashflow"]))

    rows: list[dict[str, Any]] = []
    for bucket in norm_buckets:
        rep_t = bucket.representative_t(open_ended_years=open_ended_bucket_years)
        df = float(discount_curve.discount_factor(rep_t))
        net_cf = float(net_by_bucket.get(bucket.name, 0.0))
        rows.append(
            {
                "bucket_name": bucket.name,
                "bucket_start_years": float(bucket.start_years),
                "bucket_end_years": None if bucket.end_years is None else float(bucket.end_years),
                "representative_t": float(rep_t),
                "discount_factor": df,
                "net_cashflow": net_cf,
                "pv_amount": net_cf * df,
            }
        )

    return pd.DataFrame(rows)


def evaluate_eve_bucketed(
    cashflows: pd.DataFrame,
    *,
    discount_curve_set: ForwardCurveSet,
    discount_index: str = "EUR_ESTR_OIS",
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
    open_ended_bucket_years: float = 10.0,
) -> float:
    table = build_bucketed_cashflow_table(
        cashflows,
        discount_curve_set=discount_curve_set,
        discount_index=discount_index,
        buckets=buckets,
        open_ended_bucket_years=open_ended_bucket_years,
    )
    if table.empty:
        return 0.0
    return float(table["pv_amount"].sum())


def run_eve_base(
    positions: pd.DataFrame,
    discount_curve_set: ForwardCurveSet,
    *,
    projection_curve_set: ForwardCurveSet | None = None,
    scheduled_principal_flows: pd.DataFrame | None = None,
    discount_index: str = "EUR_ESTR_OIS",
    method: str = "exact",
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
    open_ended_bucket_years: float = 10.0,
) -> float:
    projection_set = discount_curve_set if projection_curve_set is None else projection_curve_set
    if projection_set.analysis_date != discount_curve_set.analysis_date:
        raise ValueError("analysis_date must match between projection_curve_set and discount_curve_set.")

    cashflows = build_eve_cashflows(
        positions,
        analysis_date=discount_curve_set.analysis_date,
        projection_curve_set=projection_set,
        scheduled_principal_flows=scheduled_principal_flows,
    )

    m = str(method).strip().lower()
    if m == "exact":
        return evaluate_eve_exact(
            cashflows,
            discount_curve_set=discount_curve_set,
            discount_index=discount_index,
        )
    if m in {"bucketed", "bucketed_regulatory", "regulatory_bucketed"}:
        return evaluate_eve_bucketed(
            cashflows,
            discount_curve_set=discount_curve_set,
            discount_index=discount_index,
            buckets=buckets,
            open_ended_bucket_years=open_ended_bucket_years,
        )

    raise ValueError("method must be 'exact' or 'bucketed'.")


def run_eve_scenarios(
    positions: pd.DataFrame,
    base_discount_curve_set: ForwardCurveSet,
    scenario_discount_curve_sets: Mapping[str, ForwardCurveSet],
    *,
    base_projection_curve_set: ForwardCurveSet | None = None,
    scenario_projection_curve_sets: Mapping[str, ForwardCurveSet] | None = None,
    scheduled_principal_flows: pd.DataFrame | None = None,
    discount_index: str = "EUR_ESTR_OIS",
    method: str = "exact",
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
    open_ended_bucket_years: float = 10.0,
) -> EVERunResult:
    base_projection = (
        base_discount_curve_set
        if base_projection_curve_set is None
        else base_projection_curve_set
    )
    scenario_projection = (
        scenario_discount_curve_sets
        if scenario_projection_curve_sets is None
        else scenario_projection_curve_sets
    )

    base_eve = run_eve_base(
        positions,
        base_discount_curve_set,
        projection_curve_set=base_projection,
        scheduled_principal_flows=scheduled_principal_flows,
        discount_index=discount_index,
        method=method,
        buckets=buckets,
        open_ended_bucket_years=open_ended_bucket_years,
    )

    scenario_values: dict[str, float] = {}
    for scenario_name, scenario_discount_set in scenario_discount_curve_sets.items():
        if scenario_name not in scenario_projection:
            raise KeyError(
                f"Missing projection curve set for scenario {scenario_name!r}."
            )
        scenario_values[str(scenario_name)] = run_eve_base(
            positions,
            scenario_discount_set,
            projection_curve_set=scenario_projection[scenario_name],
            scheduled_principal_flows=scheduled_principal_flows,
            discount_index=discount_index,
            method=method,
            buckets=buckets,
            open_ended_bucket_years=open_ended_bucket_years,
        )

    return EVERunResult(
        analysis_date=base_discount_curve_set.analysis_date,
        method=str(method).strip().lower(),
        base_eve=float(base_eve),
        scenario_eve=scenario_values,
    )
