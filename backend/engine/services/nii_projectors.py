from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
import re
from typing import Any, Mapping

import pandas as pd
from dateutil.relativedelta import relativedelta

from engine.core.daycount import normalize_daycount_base, yearfrac
from engine.services.margin_engine import CalibratedMarginSet
from engine.services.market import ForwardCurveSet


FIXED_BULLET_REQUIRED_COLUMNS = (
    "contract_id",
    "start_date",
    "maturity_date",
    "notional",
    "side",
    "fixed_rate",
    "daycount_base",
)

FIXED_LINEAR_REQUIRED_COLUMNS = FIXED_BULLET_REQUIRED_COLUMNS

FIXED_ANNUITY_REQUIRED_COLUMNS = (
    "contract_id",
    "start_date",
    "maturity_date",
    "notional",
    "side",
    "fixed_rate",
    "daycount_base",
)

FIXED_SCHEDULED_REQUIRED_COLUMNS = FIXED_ANNUITY_REQUIRED_COLUMNS

VARIABLE_BULLET_REQUIRED_COLUMNS = (
    "contract_id",
    "start_date",
    "maturity_date",
    "notional",
    "side",
    "daycount_base",
    "index_name",
    "spread",
)

VARIABLE_LINEAR_REQUIRED_COLUMNS = VARIABLE_BULLET_REQUIRED_COLUMNS

VARIABLE_ANNUITY_REQUIRED_COLUMNS = VARIABLE_BULLET_REQUIRED_COLUMNS

VARIABLE_SCHEDULED_REQUIRED_COLUMNS = VARIABLE_BULLET_REQUIRED_COLUMNS

_ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET = "reprice_on_reset"
_ANNUITY_PAYMENT_MODE_FIXED_PAYMENT = "fixed_payment"
_SUPPORTED_ANNUITY_PAYMENT_MODES = {
    _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET,
    _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT,
}


def is_blank(value: object) -> bool:
    if pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _norm_token(value: Any) -> str | None:
    if is_blank(value):
        return None
    s = str(value).strip()
    return s if s else None


def normalise_annuity_payment_mode(
    value: object,
    *,
    row_id: object,
    field_name: str = "annuity_payment_mode",
) -> str:
    if is_blank(value):
        return _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET

    token = str(value).strip().lower()
    aliases = {
        "reprice": _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET,
        "reprice_on_reset": _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET,
        "reset_reprice": _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET,
        "fixed": _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT,
        "fixed_payment": _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT,
        "constant_payment": _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT,
        "cuota_fija": _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT,
    }
    out = aliases.get(token, token)
    if out not in _SUPPORTED_ANNUITY_PAYMENT_MODES:
        raise ValueError(
            f"Invalid value in {field_name!r} for contract_id={row_id!r}: {value!r}. "
            f"Allowed: {sorted(_SUPPORTED_ANNUITY_PAYMENT_MODES)}"
        )
    return out


def coerce_date(value: object, *, field_name: str, row_id: object) -> date:
    if isinstance(value, date):
        return value
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        raise ValueError(f"Invalid date in {field_name!r} for contract_id={row_id!r}: {value!r}")
    return dt.date()


def coerce_float(value: object, *, field_name: str, row_id: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid number in {field_name!r} for contract_id={row_id!r}: {value!r}") from exc
    if pd.isna(out):
        raise ValueError(f"Null number in {field_name!r} for contract_id={row_id!r}")
    return out


def side_sign(side: object, *, row_id: object) -> float:
    token = str(side).strip().upper()
    if token == "A":
        return 1.0
    if token == "L":
        return -1.0
    raise ValueError(f"Invalid side for contract_id={row_id!r}: {side!r} (expected 'A' or 'L')")


def ensure_required_columns(df: pd.DataFrame, required: tuple[str, ...], label: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for {label} NII: {missing}")


def _horizon_end(analysis_date: date, *, horizon_months: int = 12) -> date:
    months = int(horizon_months)
    if months <= 0:
        raise ValueError("horizon_months must be > 0")
    return analysis_date + relativedelta(months=months)


def _batch_prepare(
    positions: pd.DataFrame,
    required_columns: tuple[str, ...],
    label: str,
    analysis_date: date,
    horizon_end: date,
) -> pd.DataFrame:
    """Batch validate, coerce types, and filter to active positions.

    Returns a copy of *positions* with:
    - ``start_date``, ``maturity_date`` coerced to ``datetime.date``
    - ``notional`` (and ``fixed_rate``/``spread`` if required) coerced to float
    - ``daycount_base`` normalised to canonical string
    - ``side_sign`` column: +1.0 (asset) / -1.0 (liability)
    - ``accrual_start``, ``accrual_end`` columns (date objects)
    Only rows where ``accrual_end > accrual_start`` are returned.

    Raises ``ValueError`` with the first offending ``contract_id`` on any
    validation failure, matching the per-row error messages of the original
    ``coerce_date``/``coerce_float``/``side_sign`` helpers.
    """
    ensure_required_columns(positions, required_columns, label)
    df = positions.copy()

    # ── 1. Batch null/blank check on required columns ──────────────────
    for col in required_columns:
        s = df[col]
        blank = s.isna()
        if s.dtype == object:
            blank = blank | s.astype(str).str.strip().eq("")
        if blank.any():
            idx = df.index[blank][0]
            row_id = (
                df.at[idx, "contract_id"]
                if "contract_id" in df.columns
                else "<missing>"
            )
            raise ValueError(
                f"Required value is empty in {col!r} for contract_id={row_id!r}"
            )

    # ── 2. Coerce dates ────────────────────────────────────────────────
    start_ts = pd.to_datetime(df["start_date"], errors="coerce")
    bad = start_ts.isna()
    if bad.any():
        idx = df.index[bad][0]
        row_id = (
            df.at[idx, "contract_id"]
            if "contract_id" in df.columns
            else "<missing>"
        )
        raise ValueError(
            f"Invalid date in 'start_date' for contract_id={row_id!r}: "
            f"{df.at[idx, 'start_date']!r}"
        )

    mat_ts = pd.to_datetime(df["maturity_date"], errors="coerce")
    bad = mat_ts.isna()
    if bad.any():
        idx = df.index[bad][0]
        row_id = (
            df.at[idx, "contract_id"]
            if "contract_id" in df.columns
            else "<missing>"
        )
        raise ValueError(
            f"Invalid date in 'maturity_date' for contract_id={row_id!r}: "
            f"{df.at[idx, 'maturity_date']!r}"
        )

    # Validate maturity >= start
    bad_order = mat_ts < start_ts
    if bad_order.any():
        idx = df.index[bad_order][0]
        row_id = (
            df.at[idx, "contract_id"]
            if "contract_id" in df.columns
            else "<missing>"
        )
        raise ValueError(
            f"maturity_date < start_date for contract_id={row_id!r}: "
            f"{df.at[idx, 'start_date']} > {df.at[idx, 'maturity_date']}"
        )

    # ── 3. Coerce numerics ─────────────────────────────────────────────
    df["notional"] = pd.to_numeric(df["notional"], errors="coerce")
    bad = df["notional"].isna()
    if bad.any():
        idx = df.index[bad][0]
        row_id = (
            df.at[idx, "contract_id"]
            if "contract_id" in df.columns
            else "<missing>"
        )
        raise ValueError(
            f"Invalid number in 'notional' for contract_id={row_id!r}"
        )
    df["notional"] = df["notional"].astype(float)

    if "fixed_rate" in required_columns and "fixed_rate" in df.columns:
        df["fixed_rate"] = pd.to_numeric(df["fixed_rate"], errors="coerce")
        bad = df["fixed_rate"].isna()
        if bad.any():
            idx = df.index[bad][0]
            row_id = (
                df.at[idx, "contract_id"]
                if "contract_id" in df.columns
                else "<missing>"
            )
            raise ValueError(
                f"Invalid number in 'fixed_rate' for contract_id={row_id!r}"
            )
        df["fixed_rate"] = df["fixed_rate"].astype(float)

    if "spread" in required_columns and "spread" in df.columns:
        df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
        bad = df["spread"].isna()
        if bad.any():
            idx = df.index[bad][0]
            row_id = (
                df.at[idx, "contract_id"]
                if "contract_id" in df.columns
                else "<missing>"
            )
            raise ValueError(
                f"Invalid number in 'spread' for contract_id={row_id!r}"
            )
        df["spread"] = df["spread"].astype(float)

    # ── 4. Normalise daycount_base via unique-value lookup ─────────────
    unique_bases = df["daycount_base"].unique()
    base_map: dict = {}
    for v in unique_bases:
        try:
            base_map[v] = normalize_daycount_base(str(v))
        except ValueError:
            idx = df.index[df["daycount_base"] == v][0]
            row_id = (
                df.at[idx, "contract_id"]
                if "contract_id" in df.columns
                else "<missing>"
            )
            raise ValueError(
                f"Unrecognized daycount base for contract_id={row_id!r}: {v!r}"
            )
    df["daycount_base"] = df["daycount_base"].map(base_map)

    # ── 5. Side sign ───────────────────────────────────────────────────
    side_upper = df["side"].astype(str).str.strip().str.upper()
    bad_side = ~side_upper.isin({"A", "L"})
    if bad_side.any():
        idx = df.index[bad_side][0]
        row_id = (
            df.at[idx, "contract_id"]
            if "contract_id" in df.columns
            else "<missing>"
        )
        raise ValueError(
            f"Invalid side for contract_id={row_id!r}: "
            f"{df.at[idx, 'side']!r} (expected 'A' or 'L')"
        )
    df["side_sign"] = side_upper.map({"A": 1.0, "L": -1.0})

    # ── 6. Accrual window + filter ─────────────────────────────────────
    analysis_ts = pd.Timestamp(analysis_date)
    horizon_ts = pd.Timestamp(horizon_end)
    accrual_start_ts = start_ts.clip(lower=analysis_ts)
    accrual_end_ts = mat_ts.clip(upper=horizon_ts)

    active = accrual_end_ts > accrual_start_ts
    df = df.loc[active].copy()
    if df.empty:
        df["side_sign"] = pd.Series(dtype=float)
        df["accrual_start"] = pd.Series(dtype=object)
        df["accrual_end"] = pd.Series(dtype=object)
        return df

    df["start_date"] = start_ts.loc[active].dt.date.values
    df["maturity_date"] = mat_ts.loc[active].dt.date.values
    df["accrual_start"] = accrual_start_ts.loc[active].dt.date.values
    df["accrual_end"] = accrual_end_ts.loc[active].dt.date.values

    return df


def original_term_days(start_date: date, maturity_date: date) -> int:
    return max(1, int((maturity_date - start_date).days))


def cycle_maturity(cycle_start: date, term_days: int) -> date:
    return cycle_start + timedelta(days=max(1, int(term_days)))


def parse_frequency_token(
    value: object,
    *,
    row_id: object,
    field_name: str = "repricing_freq",
) -> tuple[int, str] | None:
    from engine.core._frequency import parse_frequency_token as _core_pft
    return _core_pft(value, strict=True, row_id=row_id, field_name=field_name)


def add_frequency(d: date, frequency: tuple[int, str]) -> date:
    from engine.core._frequency import add_frequency as _core_af
    return _core_af(d, frequency)


def build_reset_dates(
    *,
    accrual_start: date,
    accrual_end: date,
    anchor_date: date | None,
    frequency: tuple[int, str] | None,
) -> list[date]:
    # If anchor_date or frequency are missing, no intermediate resets are generated.
    # The projector will treat the variable position as fixed type during the cycle
    # (a single fixing at the start).  This is a reasonable fallback for
    # incomplete input; to detect these cases, consider
    # emitting warnings.warn() in the project_variable_*_nii_12m functions.
    if anchor_date is None or frequency is None:
        return []

    d = anchor_date
    guard = 0
    while d <= accrual_start:
        d_next = add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Unexpected loop while advancing repricing dates.")

    out: list[date] = []
    while d < accrual_end:
        out.append(d)
        d_next = add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Unexpected loop while generating repricing dates.")
    return out


def first_reset_after_accrual_start(
    *,
    accrual_start: date,
    anchor_date: date | None,
    frequency: tuple[int, str] | None,
) -> date | None:
    if anchor_date is None or frequency is None:
        return None

    d = anchor_date
    guard = 0
    while d <= accrual_start:
        d_next = add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Unexpected loop while searching for first future reset.")
    return d


def reset_occurs_on_accrual_start(
    *,
    accrual_start: date,
    anchor_date: date | None,
    frequency: tuple[int, str] | None,
) -> bool:
    if anchor_date is None or frequency is None:
        return False

    d = anchor_date
    guard = 0
    while d < accrual_start:
        d_next = add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Unexpected loop while validating reset on accrual_start.")
    return d == accrual_start


def apply_floor_cap(rate: float, floor_rate: object, cap_rate: object) -> float:
    """Applies floor/cap to the all-in rate (index + spread).

    This convention reflects the contractual behavior of retail banking products
    (mortgages, loans), where the floor/cap clause is defined on
    the final rate paid by the customer, not on the isolated index.

    If in the future there is a need to support products where floor/cap applies
    only to the index (e.g. caps on Euribor), a flag should be added per
    position (floor_cap_on_index) and apply floor/cap before adding the spread.
    """
    out = float(rate)
    if not is_blank(floor_rate):
        f = float(floor_rate)
        if isfinite(f):
            out = max(out, f)
    if not is_blank(cap_rate):
        c = float(cap_rate)
        if isfinite(c):
            out = min(out, c)
    return out


def linear_notional_at(
    d: date,
    *,
    effective_start: date,
    maturity_date: date,
    outstanding_at_effective_start: float,
) -> float:
    if d <= effective_start:
        return float(outstanding_at_effective_start)
    if d >= maturity_date:
        return 0.0

    total_days = (maturity_date - effective_start).days
    if total_days <= 0:
        return 0.0
    rem_days = (maturity_date - d).days
    return float(outstanding_at_effective_start) * (float(rem_days) / float(total_days))


def payment_frequency_or_default(row, *, row_id: object) -> tuple[int, str]:
    freq = parse_frequency_token(getattr(row, "payment_freq", None), row_id=row_id, field_name="payment_freq")
    if freq is None:
        return (1, "M")
    return freq


def build_payment_dates(
    *,
    cycle_start: date,
    cycle_maturity: date,
    payment_frequency: tuple[int, str],
) -> list[date]:
    if cycle_maturity <= cycle_start:
        return []

    dates: list[date] = []
    d = add_frequency(cycle_start, payment_frequency)
    guard = 0
    while d < cycle_maturity:
        dates.append(d)
        d_next = add_frequency(d, payment_frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Unexpected loop while generating annuity payment dates.")
    dates.append(cycle_maturity)
    return dates


def annuity_payment_amount(
    *,
    outstanding: float,
    rate: float,
    period_start: date,
    payment_dates: list[date],
    base: str,
) -> float:
    if outstanding <= 0.0:
        return 0.0
    if not payment_dates:
        return float(outstanding)

    discount = 1.0
    denom = 0.0
    prev = period_start
    for pay_date in payment_dates:
        yf = yearfrac(prev, pay_date, base)
        # Current NII engine convention:
        # - interest per period in simple: i_t = rate * yf
        # - multi-period discount as product of (1 + i_t)
        #
        # This is consistent with the rest of the projector, where the coupon is calculated
        # as balance * rate * yf in each segment.
        #
        # If another type convention is chosen (e.g. geometric effective
        # (1+rate)**yf or continuous exp(rate*yf)), it must be changed here and in the
        # interest calculation of each cycle to maintain internal consistency.
        factor = 1.0 + float(rate) * float(yf)
        if factor <= 0.0:
            factor = 1e-12
        discount *= factor
        denom += 1.0 / discount
        prev = pay_date

    if denom <= 0.0:
        return float(outstanding)
    return float(outstanding) / denom


def project_fixed_annuity_cycle(
    *,
    cycle_start: date,
    cycle_end: date,
    cycle_maturity: date,
    outstanding: float,
    sign: float,
    base: str,
    fixed_rate: float,
    payment_frequency: tuple[int, str],
) -> float:
    if cycle_end <= cycle_start or outstanding <= 0.0:
        return 0.0

    payment_dates = build_payment_dates(
        cycle_start=cycle_start,
        cycle_maturity=cycle_maturity,
        payment_frequency=payment_frequency,
    )
    payment = annuity_payment_amount(
        outstanding=outstanding,
        rate=fixed_rate,
        period_start=cycle_start,
        payment_dates=payment_dates,
        base=base,
    )

    out = 0.0
    balance = float(outstanding)
    prev = cycle_start
    for i, pay_date in enumerate(payment_dates):
        if pay_date <= prev:
            continue

        if pay_date > cycle_end:
            out += sign * balance * float(fixed_rate) * yearfrac(prev, cycle_end, base)
            break

        yf = yearfrac(prev, pay_date, base)
        interest = balance * float(fixed_rate) * yf
        out += sign * interest

        is_last_payment = i == (len(payment_dates) - 1)
        if is_last_payment:
            principal = balance
        else:
            principal = payment - interest
            if principal < 0.0:
                principal = 0.0
            if principal > balance:
                principal = balance
        balance = max(0.0, balance - principal)
        prev = pay_date

        if balance <= 1e-10:
            break

    return float(out)


def project_variable_annuity_cycle(
    *,
    cycle_start: date,
    cycle_end: date,
    cycle_maturity: date,
    outstanding: float,
    sign: float,
    base: str,
    curve_set: ForwardCurveSet,
    index_name: str,
    spread: float,
    floor_rate: object,
    cap_rate: object,
    payment_frequency: tuple[int, str],
    anchor_date: date | None,
    repricing_frequency: tuple[int, str] | None,
    fixed_rate_for_stub: float | None,
    annuity_payment_mode: str,
) -> float:
    if cycle_end <= cycle_start or outstanding <= 0.0:
        return 0.0

    payment_dates = build_payment_dates(
        cycle_start=cycle_start,
        cycle_maturity=cycle_maturity,
        payment_frequency=payment_frequency,
    )
    if not payment_dates:
        return 0.0

    reset_dates = build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=repricing_frequency,
    )
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

    def _rate_at(d: date) -> float:
        use_current_coupon = (
            (fixed_rate_for_stub is not None)
            and (not reset_at_start)
            and (first_reset_after is not None)
            and (d < first_reset_after)
        )
        if use_current_coupon:
            raw_rate = float(fixed_rate_for_stub)
        else:
            raw_rate = float(curve_set.rate_on_date(index_name, d)) + float(spread)
        return apply_floor_cap(raw_rate, floor_rate=floor_rate, cap_rate=cap_rate)

    # Legacy mode: recalculates payment at each reset (historical engine behavior).
    if annuity_payment_mode == _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET:
        regime_bounds = [cycle_start, *reset_dates, cycle_end]
        out = 0.0
        balance = float(outstanding)

        for ridx in range(len(regime_bounds) - 1):
            regime_start = regime_bounds[ridx]
            regime_end = regime_bounds[ridx + 1]
            if regime_end <= regime_start or balance <= 1e-10:
                continue

            regime_rate = _rate_at(regime_start)

            # Modeling note:
            # here the payment is recalculated at each reset. This represents products
            # where the payment is not fixed and adjusts with each repricing.
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
                if pay_date <= prev:
                    continue
                yf = yearfrac(prev, pay_date, base)
                interest = balance * regime_rate * yf
                out += sign * interest

                is_last_payment = pay_date == payment_dates[-1]
                if is_last_payment:
                    principal = balance
                else:
                    principal = payment - interest
                    if principal < 0.0:
                        principal = 0.0
                    if principal > balance:
                        principal = balance
                balance = max(0.0, balance - principal)
                prev = pay_date
                if balance <= 1e-10:
                    break

            if balance <= 1e-10:
                break
            if regime_end > prev:
                out += sign * balance * regime_rate * yearfrac(prev, regime_end, base)

        return float(out)

    # Configurable mode: fixed payment from cycle_start.
    if annuity_payment_mode == _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT:
        fixed_payment_rate = _rate_at(cycle_start)
        fixed_payment_amount = annuity_payment_amount(
            outstanding=float(outstanding),
            rate=fixed_payment_rate,
            period_start=cycle_start,
            payment_dates=payment_dates,
            base=base,
        )

        boundaries = {cycle_start, cycle_end}
        for d in reset_dates:
            if cycle_start < d < cycle_end:
                boundaries.add(d)
        for d in payment_dates:
            if cycle_start < d <= cycle_end:
                boundaries.add(d)
        ordered = sorted(boundaries)

        out = 0.0
        balance = float(outstanding)
        accrued_interest_since_payment = 0.0
        payment_date_set = set(payment_dates)

        for i in range(len(ordered) - 1):
            seg_start = ordered[i]
            seg_end = ordered[i + 1]
            if seg_end <= seg_start or balance <= 1e-10:
                continue

            seg_rate = _rate_at(seg_start)
            seg_interest = balance * seg_rate * yearfrac(seg_start, seg_end, base)
            out += sign * seg_interest
            accrued_interest_since_payment += seg_interest

            if seg_end in payment_date_set:
                is_last_payment = seg_end == payment_dates[-1]
                if is_last_payment:
                    principal = balance
                else:
                    principal = fixed_payment_amount - accrued_interest_since_payment
                    if principal < 0.0:
                        principal = 0.0
                    if principal > balance:
                        principal = balance

                balance = max(0.0, balance - principal)
                accrued_interest_since_payment = 0.0
                if balance <= 1e-10:
                    break

        return float(out)

    raise ValueError(
        f"Unsupported annuity_payment_mode: {annuity_payment_mode!r}. "
        f"Allowed: {sorted(_SUPPORTED_ANNUITY_PAYMENT_MODES)}"
    )


def lookup_margin_for_row(
    *,
    row,
    rate_type: str,
    margin_set: CalibratedMarginSet | None,
    default_margin: float,
) -> float:
    if margin_set is None:
        return float(default_margin)

    return float(
        margin_set.lookup_margin(
            rate_type=rate_type,
            source_contract_type=_norm_token(getattr(row, "source_contract_type", None)),
            side=_norm_token(getattr(row, "side", None)),
            repricing_freq=_norm_token(getattr(row, "repricing_freq", None)),
            index_name=_norm_token(getattr(row, "index_name", None)),
            default=float(default_margin),
        )
    )


def project_variable_bullet_cycle(
    *,
    cycle_start: date,
    cycle_end: date,
    notional: float,
    sign: float,
    base: str,
    index_name: str,
    spread: float,
    floor_rate: object,
    cap_rate: object,
    curve_set: ForwardCurveSet,
    anchor_date: date | None,
    frequency: tuple[int, str] | None,
    fixed_rate_for_stub: float | None,
) -> float:
    if cycle_end <= cycle_start:
        return 0.0

    reset_dates = build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    first_reset_after = first_reset_after_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    reset_at_start = reset_occurs_on_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )

    boundaries = [cycle_start, *reset_dates, cycle_end]
    out = 0.0
    for i in range(len(boundaries) - 1):
        seg_start = boundaries[i]
        seg_end = boundaries[i + 1]
        if seg_end <= seg_start:
            continue

        use_current_coupon = (
            (fixed_rate_for_stub is not None)
            and (not reset_at_start)
            and (first_reset_after is not None)
            and (seg_start < first_reset_after)
        )
        if use_current_coupon:
            seg_rate = float(fixed_rate_for_stub)
        else:
            seg_rate = float(curve_set.rate_on_date(index_name, seg_start)) + float(spread)

        seg_rate = apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)
        accrual_factor = yearfrac(seg_start, seg_end, base)
        out += sign * notional * seg_rate * accrual_factor
    return float(out)


def project_variable_linear_cycle(
    *,
    cycle_start: date,
    cycle_end: date,
    cycle_maturity: date,
    outstanding: float,
    sign: float,
    base: str,
    index_name: str,
    spread: float,
    floor_rate: object,
    cap_rate: object,
    curve_set: ForwardCurveSet,
    anchor_date: date | None,
    frequency: tuple[int, str] | None,
    fixed_rate_for_stub: float | None,
) -> float:
    if cycle_end <= cycle_start:
        return 0.0

    reset_dates = build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    first_reset_after = first_reset_after_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    reset_at_start = reset_occurs_on_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )

    boundaries = [cycle_start, *reset_dates, cycle_end]
    out = 0.0
    for i in range(len(boundaries) - 1):
        seg_start = boundaries[i]
        seg_end = boundaries[i + 1]
        if seg_end <= seg_start:
            continue

        use_current_coupon = (
            (fixed_rate_for_stub is not None)
            and (not reset_at_start)
            and (first_reset_after is not None)
            and (seg_start < first_reset_after)
        )
        if use_current_coupon:
            seg_rate = float(fixed_rate_for_stub)
        else:
            seg_rate = float(curve_set.rate_on_date(index_name, seg_start)) + float(spread)
        seg_rate = apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)

        notional_start = linear_notional_at(
            seg_start,
            effective_start=cycle_start,
            maturity_date=cycle_maturity,
            outstanding_at_effective_start=outstanding,
        )
        notional_end = linear_notional_at(
            seg_end,
            effective_start=cycle_start,
            maturity_date=cycle_maturity,
            outstanding_at_effective_start=outstanding,
        )
        avg_notional = 0.5 * (notional_start + notional_end)
        if avg_notional <= 0.0:
            continue

        accrual_factor = yearfrac(seg_start, seg_end, base)
        out += sign * avg_notional * seg_rate * accrual_factor
    return float(out)


def project_fixed_bullet_nii_12m(
    positions: pd.DataFrame,
    *,
    analysis_date: date,
    curve_set: ForwardCurveSet | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    horizon_months: int = 12,
) -> float:
    """
    NII 12m for fixed_bullet.
    If balance_constant=True and the contract matures within the horizon, it renews
    with rate = risk_free + margin.
    """
    if positions.empty:
        return 0.0
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, FIXED_BULLET_REQUIRED_COLUMNS, "fixed_bullet", analysis_date, horizon_end)
    if prep.empty:
        return 0.0

    total = 0.0
    for row in prep.itertuples(index=False):
        start_date = row.start_date
        maturity_date = row.maturity_date
        notional = row.notional
        fixed_rate = row.fixed_rate
        base = row.daycount_base
        sign = row.side_sign
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end

        total += sign * notional * fixed_rate * yearfrac(accrual_start, accrual_end, base)

        if not balance_constant or maturity_date >= horizon_end:
            continue
        if curve_set is None:
            raise ValueError("curve_set required for balance_constant in fixed_bullet")

        term_days = original_term_days(start_date, maturity_date)
        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_mat))
            renew_rate = rf + renewal_margin
            total += sign * notional * renew_rate * yearfrac(cycle_start, cycle_end, base)
            cycle_start = cycle_mat

    return float(total)


def project_fixed_linear_nii_12m(
    positions: pd.DataFrame,
    *,
    analysis_date: date,
    curve_set: ForwardCurveSet | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    horizon_months: int = 12,
) -> float:
    """
    NII 12m for fixed_linear.
    """
    if positions.empty:
        return 0.0
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, FIXED_LINEAR_REQUIRED_COLUMNS, "fixed_linear", analysis_date, horizon_end)
    if prep.empty:
        return 0.0

    total = 0.0
    for row in prep.itertuples(index=False):
        start_date = row.start_date
        maturity_date = row.maturity_date
        outstanding = row.notional
        fixed_rate = row.fixed_rate
        base = row.daycount_base
        sign = row.side_sign
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end

        n0 = linear_notional_at(
            accrual_start,
            effective_start=accrual_start,
            maturity_date=maturity_date,
            outstanding_at_effective_start=outstanding,
        )
        n1 = linear_notional_at(
            accrual_end,
            effective_start=accrual_start,
            maturity_date=maturity_date,
            outstanding_at_effective_start=outstanding,
        )
        avg_notional = 0.5 * (n0 + n1)
        total += sign * avg_notional * fixed_rate * yearfrac(accrual_start, accrual_end, base)

        if not balance_constant or maturity_date >= horizon_end:
            continue
        if curve_set is None:
            raise ValueError("curve_set required for balance_constant in fixed_linear")

        term_days = original_term_days(start_date, maturity_date)
        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_mat))
            renew_rate = rf + renewal_margin

            n0 = linear_notional_at(
                cycle_start,
                effective_start=cycle_start,
                maturity_date=cycle_mat,
                outstanding_at_effective_start=outstanding,
            )
            n1 = linear_notional_at(
                cycle_end,
                effective_start=cycle_start,
                maturity_date=cycle_mat,
                outstanding_at_effective_start=outstanding,
            )
            avg_notional = 0.5 * (n0 + n1)
            total += sign * avg_notional * renew_rate * yearfrac(cycle_start, cycle_end, base)
            cycle_start = cycle_mat

    return float(total)


def project_variable_bullet_nii_12m(
    positions: pd.DataFrame,
    *,
    analysis_date: date,
    curve_set: ForwardCurveSet,
    margin_set: CalibratedMarginSet | None = None,
    balance_constant: bool = True,
    horizon_months: int = 12,
) -> float:
    """
    NII 12m for variable_bullet.
    """
    if positions.empty:
        return 0.0
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, VARIABLE_BULLET_REQUIRED_COLUMNS, "variable_bullet", analysis_date, horizon_end)
    if prep.empty:
        return 0.0
    total = 0.0

    for row in prep.itertuples(index=False):
        row_id = row.contract_id
        start_date = row.start_date
        maturity_date = row.maturity_date
        notional = row.notional
        sign = row.side_sign
        base = row.daycount_base
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = row.spread
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = None if is_blank(getattr(row, "fixed_rate", None)) else coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)

        anchor_date = None
        if "next_reprice_date" in prep.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in prep.columns:
            frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        total += project_variable_bullet_cycle(
            cycle_start=accrual_start,
            cycle_end=accrual_end,
            notional=notional,
            sign=sign,
            base=base,
            index_name=index_name,
            spread=spread,
            floor_rate=floor_rate,
            cap_rate=cap_rate,
            curve_set=curve_set,
            anchor_date=anchor_date,
            frequency=frequency,
            fixed_rate_for_stub=fixed_rate_stub,
        )

        if not balance_constant or maturity_date >= horizon_end:
            continue

        renewal_spread = lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        term_days = original_term_days(start_date, maturity_date)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)

            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)

            total += project_variable_bullet_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                notional=notional,
                sign=sign,
                base=base,
                index_name=index_name,
                spread=renewal_spread,
                floor_rate=floor_rate,
                cap_rate=cap_rate,
                curve_set=curve_set,
                anchor_date=renewal_anchor,
                frequency=frequency,
                fixed_rate_for_stub=None,
            )
            cycle_start = cycle_mat

    return float(total)


def project_variable_linear_nii_12m(
    positions: pd.DataFrame,
    *,
    analysis_date: date,
    curve_set: ForwardCurveSet,
    margin_set: CalibratedMarginSet | None = None,
    balance_constant: bool = True,
    horizon_months: int = 12,
) -> float:
    """
    NII 12m for variable_linear.
    """
    if positions.empty:
        return 0.0
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, VARIABLE_LINEAR_REQUIRED_COLUMNS, "variable_linear", analysis_date, horizon_end)
    if prep.empty:
        return 0.0
    total = 0.0

    for row in prep.itertuples(index=False):
        row_id = row.contract_id
        start_date = row.start_date
        maturity_date = row.maturity_date
        outstanding = row.notional
        sign = row.side_sign
        base = row.daycount_base
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = row.spread
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = None if is_blank(getattr(row, "fixed_rate", None)) else coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)

        anchor_date = None
        if "next_reprice_date" in prep.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in prep.columns:
            frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        total += project_variable_linear_cycle(
            cycle_start=accrual_start,
            cycle_end=accrual_end,
            cycle_maturity=maturity_date,
            outstanding=outstanding,
            sign=sign,
            base=base,
            index_name=index_name,
            spread=spread,
            floor_rate=floor_rate,
            cap_rate=cap_rate,
            curve_set=curve_set,
            anchor_date=anchor_date,
            frequency=frequency,
            fixed_rate_for_stub=fixed_rate_stub,
        )

        if not balance_constant or maturity_date >= horizon_end:
            continue

        renewal_spread = lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        term_days = original_term_days(start_date, maturity_date)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)

            total += project_variable_linear_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                cycle_maturity=cycle_mat,
                outstanding=outstanding,
                sign=sign,
                base=base,
                index_name=index_name,
                spread=renewal_spread,
                floor_rate=floor_rate,
                cap_rate=cap_rate,
                curve_set=curve_set,
                anchor_date=renewal_anchor,
                frequency=frequency,
                fixed_rate_for_stub=None,
            )
            cycle_start = cycle_mat

    return float(total)


def project_fixed_annuity_nii_12m(
    positions: pd.DataFrame,
    *,
    analysis_date: date,
    curve_set: ForwardCurveSet | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    horizon_months: int = 12,
) -> float:
    """
    NII 12m for fixed_annuity (French-style payment by default).
    """
    if positions.empty:
        return 0.0
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, FIXED_ANNUITY_REQUIRED_COLUMNS, "fixed_annuity", analysis_date, horizon_end)
    if prep.empty:
        return 0.0

    total = 0.0
    for row in prep.itertuples(index=False):
        start_date = row.start_date
        maturity_date = row.maturity_date
        outstanding = row.notional
        fixed_rate = row.fixed_rate
        base = row.daycount_base
        sign = row.side_sign
        payment_frequency = payment_frequency_or_default(row, row_id=row.contract_id)
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end

        total += project_fixed_annuity_cycle(
            cycle_start=accrual_start,
            cycle_end=accrual_end,
            cycle_maturity=maturity_date,
            outstanding=outstanding,
            sign=sign,
            base=base,
            fixed_rate=fixed_rate,
            payment_frequency=payment_frequency,
        )

        if not balance_constant or maturity_date >= horizon_end:
            continue
        if curve_set is None:
            raise ValueError("curve_set required for balance_constant in fixed_annuity")

        term_days = original_term_days(start_date, maturity_date)
        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_mat))
            renew_rate = rf + renewal_margin
            total += project_fixed_annuity_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                cycle_maturity=cycle_mat,
                outstanding=outstanding,
                sign=sign,
                base=base,
                fixed_rate=renew_rate,
                payment_frequency=payment_frequency,
            )
            cycle_start = cycle_mat

    return float(total)


def project_variable_annuity_nii_12m(
    positions: pd.DataFrame,
    *,
    analysis_date: date,
    curve_set: ForwardCurveSet,
    margin_set: CalibratedMarginSet | None = None,
    balance_constant: bool = True,
    horizon_months: int = 12,
    annuity_payment_mode: str = _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET,
) -> float:
    """
    NII 12m for variable_annuity.

    Payment mode (configurable):
    - reprice_on_reset (default/legacy): recalculates the payment at each reset.
    - fixed_payment: keeps payment fixed from start of cycle.

    If column `annuity_payment_mode` exists per contract, it overrides
    the global parameter.
    """
    if positions.empty:
        return 0.0
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, VARIABLE_ANNUITY_REQUIRED_COLUMNS, "variable_annuity", analysis_date, horizon_end)
    if prep.empty:
        return 0.0
    # Backward compatibility: if nothing is configured, we keep
    # exactly the historical behavior (reprice_on_reset).
    global_annuity_payment_mode = normalise_annuity_payment_mode(
        annuity_payment_mode,
        row_id="<global>",
        field_name="annuity_payment_mode",
    )
    total = 0.0

    for row in prep.itertuples(index=False):
        row_id = row.contract_id
        start_date = row.start_date
        maturity_date = row.maturity_date
        outstanding = row.notional
        sign = row.side_sign
        base = row.daycount_base
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end
        payment_frequency = payment_frequency_or_default(row, row_id=row_id)

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = row.spread
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = (
            None
            if is_blank(getattr(row, "fixed_rate", None))
            else coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)
        )

        anchor_date = None
        if "next_reprice_date" in prep.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in prep.columns:
            frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        row_annuity_payment_mode = global_annuity_payment_mode
        if "annuity_payment_mode" in prep.columns and not is_blank(getattr(row, "annuity_payment_mode", None)):
            # Override per contract for banks/products with mixed rules.
            row_annuity_payment_mode = normalise_annuity_payment_mode(
                getattr(row, "annuity_payment_mode", None),
                row_id=row_id,
            )

        total += project_variable_annuity_cycle(
            cycle_start=accrual_start,
            cycle_end=accrual_end,
            cycle_maturity=maturity_date,
            outstanding=outstanding,
            sign=sign,
            base=base,
            curve_set=curve_set,
            index_name=index_name,
            spread=spread,
            floor_rate=floor_rate,
            cap_rate=cap_rate,
            payment_frequency=payment_frequency,
            anchor_date=anchor_date,
            repricing_frequency=frequency,
            fixed_rate_for_stub=fixed_rate_stub,
            annuity_payment_mode=row_annuity_payment_mode,
        )

        if not balance_constant or maturity_date >= horizon_end:
            continue

        renewal_spread = lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        term_days = original_term_days(start_date, maturity_date)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)

            total += project_variable_annuity_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                cycle_maturity=cycle_mat,
                outstanding=outstanding,
                sign=sign,
                base=base,
                curve_set=curve_set,
                index_name=index_name,
                spread=renewal_spread,
                floor_rate=floor_rate,
                cap_rate=cap_rate,
                payment_frequency=payment_frequency,
                anchor_date=renewal_anchor,
                repricing_frequency=frequency,
                fixed_rate_for_stub=None,
                annuity_payment_mode=row_annuity_payment_mode,
            )
            cycle_start = cycle_mat

    return float(total)


def prepare_scheduled_principal_flows(
    principal_flows: pd.DataFrame | None,
) -> dict[str, list[tuple[date, float]]]:
    if principal_flows is None:
        raise ValueError(
            "principal_flows is required to project source_contract_type scheduled."
        )
    if principal_flows.empty:
        return {}

    required = ("contract_id", "flow_date", "principal_amount")
    missing = [c for c in required if c not in principal_flows.columns]
    if missing:
        raise ValueError(f"principal_flows missing required columns: {missing}")

    pf = principal_flows.copy()
    pf["contract_id"] = pf["contract_id"].astype("string").str.strip()
    invalid_id = pf["contract_id"].isna() | pf["contract_id"].eq("")
    if invalid_id.any():
        rows = [int(i) + 2 for i in pf.index[invalid_id][:10].tolist()]
        raise ValueError(f"principal_flows with empty contract_id in rows {rows}")

    parsed_dates = pd.to_datetime(pf["flow_date"], errors="coerce").dt.date
    invalid_date = parsed_dates.isna()
    if invalid_date.any():
        rows = [int(i) + 2 for i in pf.index[invalid_date][:10].tolist()]
        raise ValueError(f"principal_flows with invalid flow_date in rows {rows}")
    pf["flow_date"] = parsed_dates

    parsed_amount = pd.to_numeric(pf["principal_amount"], errors="coerce")
    invalid_amount = parsed_amount.isna()
    if invalid_amount.any():
        rows = [int(i) + 2 for i in pf.index[invalid_amount][:10].tolist()]
        raise ValueError(f"principal_flows with invalid principal_amount in rows {rows}")
    pf["principal_amount"] = parsed_amount.astype(float)

    grouped = (
        pf.groupby(["contract_id", "flow_date"], as_index=False)["principal_amount"]
        .sum()
        .sort_values(["contract_id", "flow_date"], kind="stable")
    )

    out: dict[str, list[tuple[date, float]]] = {}
    for contract_id, g in grouped.groupby("contract_id", sort=False):
        out[str(contract_id)] = [
            (d, float(a))
            for d, a in zip(g["flow_date"].tolist(), g["principal_amount"].tolist())
        ]
    return out


def scheduled_flow_map_for_window(
    contract_flows: list[tuple[date, float]],
    *,
    cycle_start: date,
    cycle_end: date,
) -> dict[date, float]:
    """Filters principal flows in the half-open interval (cycle_start, cycle_end].

    Flows at cycle_start are excluded because they represent amortizations already
    occurred whose effect is already reflected in the outstanding balance of
    in input.  Flows at cycle_end are included to capture the return
    at maturity.  This convention is standard in cashflow engines.
    """
    out: dict[date, float] = {}
    if cycle_end <= cycle_start:
        return out
    for flow_date, amount in contract_flows:
        if flow_date <= cycle_start or flow_date > cycle_end:
            continue
        out[flow_date] = out.get(flow_date, 0.0) + float(amount)
    return out


def apply_principal_flow(balance: float, principal_amount: float) -> float:
    out = float(balance) - float(principal_amount)
    if out < 0.0:
        return 0.0
    return out


def scheduled_template_from_remaining_flows(
    contract_flows: list[tuple[date, float]],
    *,
    accrual_start: date,
    maturity_date: date,
    outstanding: float,
) -> list[tuple[int, float]]:
    template: list[tuple[int, float]] = []
    for flow_date, amount in contract_flows:
        if flow_date <= accrual_start or flow_date > maturity_date:
            continue
        offset_days = (flow_date - accrual_start).days
        if offset_days <= 0:
            continue
        template.append((int(offset_days), float(amount)))

    if not template:
        rem_days = max(1, int((maturity_date - accrual_start).days))
        return [(rem_days, float(outstanding))]

    total = float(sum(a for _, a in template))
    if abs(total) <= 1e-12:
        rem_days = max(1, int((maturity_date - accrual_start).days))
        return [(rem_days, float(outstanding))]

    scale = float(outstanding) / total
    return [(d, float(a) * scale) for d, a in template]


def template_term_days(template: list[tuple[int, float]]) -> int:
    if not template:
        return 1
    return max(1, max(int(d) for d, _ in template))


def scheduled_flow_map_from_template(
    *,
    cycle_start: date,
    cycle_end: date,
    template: list[tuple[int, float]],
) -> dict[date, float]:
    out: dict[date, float] = {}
    for offset_days, amount in template:
        d = cycle_start + timedelta(days=max(1, int(offset_days)))
        if d <= cycle_start or d > cycle_end:
            continue
        out[d] = out.get(d, 0.0) + float(amount)
    return out


def project_fixed_scheduled_cycle(
    *,
    cycle_start: date,
    cycle_end: date,
    outstanding: float,
    sign: float,
    base: str,
    fixed_rate: float,
    principal_flow_map: Mapping[date, float],
) -> float:
    if cycle_end <= cycle_start or outstanding <= 0.0:
        return 0.0

    # Principal flows in (cycle_start, cycle_end] — half-open convention
    # consistent with scheduled_flow_map_for_window.
    boundaries = {cycle_start, cycle_end}
    for d in principal_flow_map.keys():
        if cycle_start < d <= cycle_end:
            boundaries.add(d)
    ordered = sorted(boundaries)

    out = 0.0
    balance = float(outstanding)
    for i in range(len(ordered) - 1):
        seg_start = ordered[i]
        seg_end = ordered[i + 1]
        if seg_end <= seg_start:
            continue

        # Interest accrued on the outstanding balance during the segment.
        # Principal is applied at the end of the segment, after accumulating interest.
        out += sign * balance * float(fixed_rate) * yearfrac(seg_start, seg_end, base)
        principal_at_end = float(principal_flow_map.get(seg_end, 0.0))
        if principal_at_end != 0.0:
            balance = apply_principal_flow(balance, principal_at_end)
        if balance <= 1e-10:
            break

    return float(out)


def project_variable_scheduled_cycle(
    *,
    cycle_start: date,
    cycle_end: date,
    outstanding: float,
    sign: float,
    base: str,
    curve_set: ForwardCurveSet,
    index_name: str,
    spread: float,
    floor_rate: object,
    cap_rate: object,
    anchor_date: date | None,
    frequency: tuple[int, str] | None,
    fixed_rate_for_stub: float | None,
    principal_flow_map: Mapping[date, float],
) -> float:
    if cycle_end <= cycle_start or outstanding <= 0.0:
        return 0.0

    reset_dates = build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    first_reset_after = first_reset_after_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    reset_at_start = reset_occurs_on_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )

    # Principal flows in (cycle_start, cycle_end] — half-open convention
    # consistent with scheduled_flow_map_for_window.
    boundaries = {cycle_start, cycle_end}
    for d in reset_dates:
        if cycle_start < d < cycle_end:
            boundaries.add(d)
    for d in principal_flow_map.keys():
        if cycle_start < d <= cycle_end:
            boundaries.add(d)
    ordered = sorted(boundaries)

    out = 0.0
    balance = float(outstanding)
    for i in range(len(ordered) - 1):
        seg_start = ordered[i]
        seg_end = ordered[i + 1]
        if seg_end <= seg_start or balance <= 1e-10:
            continue

        use_current_coupon = (
            (fixed_rate_for_stub is not None)
            and (not reset_at_start)
            and (first_reset_after is not None)
            and (seg_start < first_reset_after)
        )
        if use_current_coupon:
            seg_rate = float(fixed_rate_for_stub)
        else:
            seg_rate = float(curve_set.rate_on_date(index_name, seg_start)) + float(spread)
        seg_rate = apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)

        # Interest accrued on the outstanding balance during the segment.
        # Principal is applied at the end of the segment, after accumulating interest.
        out += sign * balance * seg_rate * yearfrac(seg_start, seg_end, base)

        principal_at_end = float(principal_flow_map.get(seg_end, 0.0))
        if principal_at_end != 0.0:
            balance = apply_principal_flow(balance, principal_at_end)
        if balance <= 1e-10:
            break

    return float(out)


def project_fixed_scheduled_nii_12m(
    positions: pd.DataFrame,
    *,
    principal_flows: pd.DataFrame | None,
    analysis_date: date,
    curve_set: ForwardCurveSet | None = None,
    margin_set: CalibratedMarginSet | None = None,
    risk_free_index: str = "EUR_ESTR_OIS",
    balance_constant: bool = True,
    horizon_months: int = 12,
) -> float:
    """
    NII 12m for fixed_scheduled using explicit principal flows.
    """
    if positions.empty:
        return 0.0
    flows_by_contract = prepare_scheduled_principal_flows(principal_flows)
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, FIXED_SCHEDULED_REQUIRED_COLUMNS, "fixed_scheduled", analysis_date, horizon_end)
    if prep.empty:
        return 0.0

    total = 0.0
    for row in prep.itertuples(index=False):
        contract_id = str(row.contract_id).strip()
        contract_flows = flows_by_contract.get(contract_id, [])

        start_date = row.start_date
        maturity_date = row.maturity_date
        outstanding = row.notional
        fixed_rate = row.fixed_rate
        base = row.daycount_base
        sign = row.side_sign
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end

        flow_map = scheduled_flow_map_for_window(
            contract_flows,
            cycle_start=accrual_start,
            cycle_end=accrual_end,
        )
        total += project_fixed_scheduled_cycle(
            cycle_start=accrual_start,
            cycle_end=accrual_end,
            outstanding=outstanding,
            sign=sign,
            base=base,
            fixed_rate=fixed_rate,
            principal_flow_map=flow_map,
        )

        if not balance_constant or maturity_date >= horizon_end:
            continue
        if curve_set is None:
            raise ValueError("curve_set required for balance_constant in fixed_scheduled")

        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        template = scheduled_template_from_remaining_flows(
            contract_flows,
            accrual_start=accrual_start,
            maturity_date=maturity_date,
            outstanding=outstanding,
        )
        term_days = template_term_days(template)

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_mat))
            renew_rate = rf + renewal_margin

            flow_map = scheduled_flow_map_from_template(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                template=template,
            )
            total += project_fixed_scheduled_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                outstanding=outstanding,
                sign=sign,
                base=base,
                fixed_rate=renew_rate,
                principal_flow_map=flow_map,
            )
            cycle_start = cycle_mat

    return float(total)


def project_variable_scheduled_nii_12m(
    positions: pd.DataFrame,
    *,
    principal_flows: pd.DataFrame | None,
    analysis_date: date,
    curve_set: ForwardCurveSet,
    margin_set: CalibratedMarginSet | None = None,
    balance_constant: bool = True,
    horizon_months: int = 12,
) -> float:
    """
    NII 12m for variable_scheduled using explicit principal flows.
    """
    if positions.empty:
        return 0.0
    flows_by_contract = prepare_scheduled_principal_flows(principal_flows)
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    prep = _batch_prepare(positions, VARIABLE_SCHEDULED_REQUIRED_COLUMNS, "variable_scheduled", analysis_date, horizon_end)
    if prep.empty:
        return 0.0
    total = 0.0

    for row in prep.itertuples(index=False):
        row_id = row.contract_id
        contract_id = str(row.contract_id).strip()
        contract_flows = flows_by_contract.get(contract_id, [])

        start_date = row.start_date
        maturity_date = row.maturity_date
        outstanding = row.notional
        sign = row.side_sign
        base = row.daycount_base
        accrual_start = row.accrual_start
        accrual_end = row.accrual_end

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = row.spread
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = (
            None
            if is_blank(getattr(row, "fixed_rate", None))
            else coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)
        )

        anchor_date = None
        if "next_reprice_date" in prep.columns and not is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in prep.columns:
            frequency = parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        flow_map = scheduled_flow_map_for_window(
            contract_flows,
            cycle_start=accrual_start,
            cycle_end=accrual_end,
        )
        total += project_variable_scheduled_cycle(
            cycle_start=accrual_start,
            cycle_end=accrual_end,
            outstanding=outstanding,
            sign=sign,
            base=base,
            curve_set=curve_set,
            index_name=index_name,
            spread=spread,
            floor_rate=floor_rate,
            cap_rate=cap_rate,
            anchor_date=anchor_date,
            frequency=frequency,
            fixed_rate_for_stub=fixed_rate_stub,
            principal_flow_map=flow_map,
        )

        if not balance_constant or maturity_date >= horizon_end:
            continue

        renewal_spread = lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        template = scheduled_template_from_remaining_flows(
            contract_flows,
            accrual_start=accrual_start,
            maturity_date=maturity_date,
            outstanding=outstanding,
        )
        term_days = template_term_days(template)

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_mat = cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_mat, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = add_frequency(cycle_start, frequency)

            flow_map = scheduled_flow_map_from_template(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                template=template,
            )
            total += project_variable_scheduled_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                outstanding=outstanding,
                sign=sign,
                base=base,
                curve_set=curve_set,
                index_name=index_name,
                spread=renewal_spread,
                floor_rate=floor_rate,
                cap_rate=cap_rate,
                anchor_date=renewal_anchor,
                frequency=frequency,
                fixed_rate_for_stub=None,
                principal_flow_map=flow_map,
            )
            cycle_start = cycle_mat

    return float(total)
