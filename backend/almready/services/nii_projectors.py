from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
import re
from typing import Any, Mapping

import pandas as pd
from dateutil.relativedelta import relativedelta

from almready.core.daycount import normalizar_base_de_calculo, yearfrac
from almready.services.margin_engine import CalibratedMarginSet
from almready.services.market import ForwardCurveSet


_FIXED_BULLET_REQUIRED_COLUMNS = (
    "contract_id",
    "start_date",
    "maturity_date",
    "notional",
    "side",
    "fixed_rate",
    "daycount_base",
)

_FIXED_LINEAR_REQUIRED_COLUMNS = _FIXED_BULLET_REQUIRED_COLUMNS

_FIXED_ANNUITY_REQUIRED_COLUMNS = (
    "contract_id",
    "start_date",
    "maturity_date",
    "notional",
    "side",
    "fixed_rate",
    "daycount_base",
)

_FIXED_SCHEDULED_REQUIRED_COLUMNS = _FIXED_ANNUITY_REQUIRED_COLUMNS

_VARIABLE_BULLET_REQUIRED_COLUMNS = (
    "contract_id",
    "start_date",
    "maturity_date",
    "notional",
    "side",
    "daycount_base",
    "index_name",
    "spread",
)

_VARIABLE_LINEAR_REQUIRED_COLUMNS = _VARIABLE_BULLET_REQUIRED_COLUMNS

_VARIABLE_ANNUITY_REQUIRED_COLUMNS = _VARIABLE_BULLET_REQUIRED_COLUMNS

_VARIABLE_SCHEDULED_REQUIRED_COLUMNS = _VARIABLE_BULLET_REQUIRED_COLUMNS

_ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET = "reprice_on_reset"
_ANNUITY_PAYMENT_MODE_FIXED_PAYMENT = "fixed_payment"
_SUPPORTED_ANNUITY_PAYMENT_MODES = {
    _ANNUITY_PAYMENT_MODE_REPRICE_ON_RESET,
    _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT,
}


def _is_blank(value: object) -> bool:
    if pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _norm_token(value: Any) -> str | None:
    if _is_blank(value):
        return None
    s = str(value).strip()
    return s if s else None


def _normalise_annuity_payment_mode(
    value: object,
    *,
    row_id: object,
    field_name: str = "annuity_payment_mode",
) -> str:
    if _is_blank(value):
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
            f"Valor invalido en {field_name!r} para contract_id={row_id!r}: {value!r}. "
            f"Permitidos: {sorted(_SUPPORTED_ANNUITY_PAYMENT_MODES)}"
        )
    return out


def _coerce_date(value: object, *, field_name: str, row_id: object) -> date:
    if isinstance(value, date):
        return value
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        raise ValueError(f"Fecha invalida en {field_name!r} para contract_id={row_id!r}: {value!r}")
    return dt.date()


def _coerce_float(value: object, *, field_name: str, row_id: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Numero invalido en {field_name!r} para contract_id={row_id!r}: {value!r}") from exc
    if pd.isna(out):
        raise ValueError(f"Numero nulo en {field_name!r} para contract_id={row_id!r}")
    return out


def _side_sign(side: object, *, row_id: object) -> float:
    token = str(side).strip().upper()
    if token == "A":
        return 1.0
    if token == "L":
        return -1.0
    raise ValueError(f"side invalido para contract_id={row_id!r}: {side!r} (esperado 'A' o 'L')")


def _ensure_required_columns(df: pd.DataFrame, required: tuple[str, ...], label: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas para {label} NII: {missing}")


def _horizon_end(analysis_date: date, *, horizon_months: int = 12) -> date:
    months = int(horizon_months)
    if months <= 0:
        raise ValueError("horizon_months debe ser > 0")
    return analysis_date + relativedelta(months=months)


def _original_term_days(start_date: date, maturity_date: date) -> int:
    return max(1, int((maturity_date - start_date).days))


def _cycle_maturity(cycle_start: date, term_days: int) -> date:
    return cycle_start + timedelta(days=max(1, int(term_days)))


def _parse_frequency_token(
    value: object,
    *,
    row_id: object,
    field_name: str = "repricing_freq",
) -> tuple[int, str] | None:
    if _is_blank(value):
        return None

    token = str(value).strip().upper().replace(" ", "")
    if token in {"0D", "0W", "0M", "0Y"}:
        return None
    if token in {"ON", "O/N"}:
        return (1, "D")

    m = re.match(r"^(\d+)([DWMY])$", token)
    if not m:
        raise ValueError(
            f"Frecuencia invalida en {field_name!r} para contract_id={row_id!r}: {value!r}"
        )

    n = int(m.group(1))
    unit = m.group(2)
    if n <= 0:
        return None
    return (n, unit)


def _add_frequency(d: date, frequency: tuple[int, str]) -> date:
    n, unit = frequency
    if unit == "D":
        return d + relativedelta(days=n)
    if unit == "W":
        return d + relativedelta(weeks=n)
    if unit == "M":
        return d + relativedelta(months=n)
    if unit == "Y":
        return d + relativedelta(years=n)
    raise ValueError(f"Unidad de frecuencia no soportada: {unit!r}")


def _build_reset_dates(
    *,
    accrual_start: date,
    accrual_end: date,
    anchor_date: date | None,
    frequency: tuple[int, str] | None,
) -> list[date]:
    # Si faltan anchor_date o frequency, no se generan resets intermedios.
    # El proyector tratara la posicion variable como tipo fijo durante el ciclo
    # (un unico fixing al inicio).  Esto es un fallback razonable ante datos
    # de entrada incompletos; si se quiere detectar estos casos, considerar
    # emitir warnings.warn() en las funciones project_variable_*_nii_12m.
    if anchor_date is None or frequency is None:
        return []

    d = anchor_date
    guard = 0
    while d <= accrual_start:
        d_next = _add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Bucle inesperado al avanzar fechas de repricing.")

    out: list[date] = []
    while d < accrual_end:
        out.append(d)
        d_next = _add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Bucle inesperado al generar fechas de repricing.")
    return out


def _first_reset_after_accrual_start(
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
        d_next = _add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Bucle inesperado al buscar primer reset futuro.")
    return d


def _reset_occurs_on_accrual_start(
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
        d_next = _add_frequency(d, frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Bucle inesperado al validar reset en accrual_start.")
    return d == accrual_start


def _apply_floor_cap(rate: float, floor_rate: object, cap_rate: object) -> float:
    """Aplica floor/cap al tipo all-in (index + spread).

    Esta convencion refleja el comportamiento contractual de productos bancarios
    retail (hipotecas, prestamos), donde la clausula suelo/techo se define sobre
    el tipo final que paga el cliente, no sobre el indice aislado.

    Si en el futuro se necesita soportar productos donde el floor/cap aplica
    solo al indice (p.ej. caps sobre Euribor), se deberia anadir un flag por
    posicion (floor_cap_on_index) y aplicar floor/cap antes de sumar el spread.
    """
    out = float(rate)
    if not _is_blank(floor_rate):
        f = float(floor_rate)
        if isfinite(f):
            out = max(out, f)
    if not _is_blank(cap_rate):
        c = float(cap_rate)
        if isfinite(c):
            out = min(out, c)
    return out


def _linear_notional_at(
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


def _payment_frequency_or_default(row, *, row_id: object) -> tuple[int, str]:
    freq = _parse_frequency_token(getattr(row, "payment_freq", None), row_id=row_id, field_name="payment_freq")
    if freq is None:
        return (1, "M")
    return freq


def _build_payment_dates(
    *,
    cycle_start: date,
    cycle_maturity: date,
    payment_frequency: tuple[int, str],
) -> list[date]:
    if cycle_maturity <= cycle_start:
        return []

    dates: list[date] = []
    d = _add_frequency(cycle_start, payment_frequency)
    guard = 0
    while d < cycle_maturity:
        dates.append(d)
        d_next = _add_frequency(d, payment_frequency)
        if d_next <= d:
            break
        d = d_next
        guard += 1
        if guard > 10_000:
            raise RuntimeError("Bucle inesperado al generar fechas de pago annuity.")
    dates.append(cycle_maturity)
    return dates


def _annuity_payment_amount(
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
        # Convencion actual del motor NII:
        # - interes por periodo en simple: i_t = rate * yf
        # - descuento multiperiodo como producto de (1 + i_t)
        #
        # Esto es coherente con el resto del proyector, donde el cupon se calcula
        # como balance * rate * yf en cada tramo.
        #
        # Si se decide usar otra convencion de tipo (p.ej. efectiva geometrica
        # (1+rate)**yf o continua exp(rate*yf)), debe cambiarse aqui y en el
        # calculo de intereses de cada ciclo para mantener consistencia interna.
        factor = 1.0 + float(rate) * float(yf)
        if factor <= 0.0:
            factor = 1e-12
        discount *= factor
        denom += 1.0 / discount
        prev = pay_date

    if denom <= 0.0:
        return float(outstanding)
    return float(outstanding) / denom


def _project_fixed_annuity_cycle(
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

    payment_dates = _build_payment_dates(
        cycle_start=cycle_start,
        cycle_maturity=cycle_maturity,
        payment_frequency=payment_frequency,
    )
    payment = _annuity_payment_amount(
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


def _project_variable_annuity_cycle(
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

    payment_dates = _build_payment_dates(
        cycle_start=cycle_start,
        cycle_maturity=cycle_maturity,
        payment_frequency=payment_frequency,
    )
    if not payment_dates:
        return 0.0

    reset_dates = _build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=repricing_frequency,
    )
    first_reset_after = _first_reset_after_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=repricing_frequency,
    )
    reset_at_start = _reset_occurs_on_accrual_start(
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
        return _apply_floor_cap(raw_rate, floor_rate=floor_rate, cap_rate=cap_rate)

    # Modo legacy: se recalcula cuota en cada reset (comportamiento historico del motor).
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

            # Nota de modelizacion:
            # aqui se recalcula la cuota en cada reset. Esto representa productos
            # donde la cuota no es fija y se ajusta con cada reprecio.
            remaining_payment_dates = [d for d in payment_dates if d > regime_start]
            if not remaining_payment_dates:
                break
            payment = _annuity_payment_amount(
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

    # Modo configurable: cuota fija desde cycle_start.
    if annuity_payment_mode == _ANNUITY_PAYMENT_MODE_FIXED_PAYMENT:
        fixed_payment_rate = _rate_at(cycle_start)
        fixed_payment_amount = _annuity_payment_amount(
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
        f"annuity_payment_mode no soportado: {annuity_payment_mode!r}. "
        f"Permitidos: {sorted(_SUPPORTED_ANNUITY_PAYMENT_MODES)}"
    )


def _lookup_margin_for_row(
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


def _project_variable_bullet_cycle(
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

    reset_dates = _build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    first_reset_after = _first_reset_after_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    reset_at_start = _reset_occurs_on_accrual_start(
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

        seg_rate = _apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)
        accrual_factor = yearfrac(seg_start, seg_end, base)
        out += sign * notional * seg_rate * accrual_factor
    return float(out)


def _project_variable_linear_cycle(
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

    reset_dates = _build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    first_reset_after = _first_reset_after_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    reset_at_start = _reset_occurs_on_accrual_start(
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
        seg_rate = _apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)

        notional_start = _linear_notional_at(
            seg_start,
            effective_start=cycle_start,
            maturity_date=cycle_maturity,
            outstanding_at_effective_start=outstanding,
        )
        notional_end = _linear_notional_at(
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
    NII 12m para fixed_bullet.
    Si balance_constant=True y el contrato vence dentro del horizonte, se renueva
    con rate = risk_free + margin.
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _FIXED_BULLET_REQUIRED_COLUMNS, "fixed_bullet")
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)

    total = 0.0
    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _FIXED_BULLET_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        notional = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = _coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))
        sign = _side_sign(row.side, row_id=row_id)

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        total += sign * notional * fixed_rate * yearfrac(accrual_start, accrual_end, base)

        if not balance_constant or maturity_date >= horizon_end:
            continue
        if curve_set is None:
            raise ValueError("curve_set requerido para balance_constant en fixed_bullet")

        term_days = _original_term_days(start_date, maturity_date)
        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = _lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_maturity))
            renew_rate = rf + renewal_margin
            total += sign * notional * renew_rate * yearfrac(cycle_start, cycle_end, base)
            cycle_start = cycle_maturity

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
    NII 12m para fixed_linear.
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _FIXED_LINEAR_REQUIRED_COLUMNS, "fixed_linear")
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)

    total = 0.0
    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _FIXED_LINEAR_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        outstanding = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = _coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))
        sign = _side_sign(row.side, row_id=row_id)

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        n0 = _linear_notional_at(
            accrual_start,
            effective_start=accrual_start,
            maturity_date=maturity_date,
            outstanding_at_effective_start=outstanding,
        )
        n1 = _linear_notional_at(
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
            raise ValueError("curve_set requerido para balance_constant en fixed_linear")

        term_days = _original_term_days(start_date, maturity_date)
        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = _lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_maturity))
            renew_rate = rf + renewal_margin

            n0 = _linear_notional_at(
                cycle_start,
                effective_start=cycle_start,
                maturity_date=cycle_maturity,
                outstanding_at_effective_start=outstanding,
            )
            n1 = _linear_notional_at(
                cycle_end,
                effective_start=cycle_start,
                maturity_date=cycle_maturity,
                outstanding_at_effective_start=outstanding,
            )
            avg_notional = 0.5 * (n0 + n1)
            total += sign * avg_notional * renew_rate * yearfrac(cycle_start, cycle_end, base)
            cycle_start = cycle_maturity

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
    NII 12m para variable_bullet.
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _VARIABLE_BULLET_REQUIRED_COLUMNS, "variable_bullet")
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    total = 0.0

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _VARIABLE_BULLET_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        notional = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        sign = _side_sign(row.side, row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = _coerce_float(row.spread, field_name="spread", row_id=row_id)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = None if _is_blank(getattr(row, "fixed_rate", None)) else _coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)

        anchor_date = None
        if "next_reprice_date" in positions.columns and not _is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = _coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in positions.columns:
            frequency = _parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        total += _project_variable_bullet_cycle(
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

        renewal_spread = _lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        term_days = _original_term_days(start_date, maturity_date)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)

            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = _add_frequency(cycle_start, frequency)

            total += _project_variable_bullet_cycle(
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
            cycle_start = cycle_maturity

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
    NII 12m para variable_linear.
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _VARIABLE_LINEAR_REQUIRED_COLUMNS, "variable_linear")
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    total = 0.0

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _VARIABLE_LINEAR_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        outstanding = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        sign = _side_sign(row.side, row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = _coerce_float(row.spread, field_name="spread", row_id=row_id)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = None if _is_blank(getattr(row, "fixed_rate", None)) else _coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)

        anchor_date = None
        if "next_reprice_date" in positions.columns and not _is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = _coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in positions.columns:
            frequency = _parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        total += _project_variable_linear_cycle(
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

        renewal_spread = _lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        term_days = _original_term_days(start_date, maturity_date)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = _add_frequency(cycle_start, frequency)

            total += _project_variable_linear_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                cycle_maturity=cycle_maturity,
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
            cycle_start = cycle_maturity

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
    NII 12m para fixed_annuity (cuota estilo francesa por defecto).
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _FIXED_ANNUITY_REQUIRED_COLUMNS, "fixed_annuity")
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)

    total = 0.0
    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _FIXED_ANNUITY_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        outstanding = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = _coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))
        sign = _side_sign(row.side, row_id=row_id)
        payment_frequency = _payment_frequency_or_default(row, row_id=row_id)

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        total += _project_fixed_annuity_cycle(
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
            raise ValueError("curve_set requerido para balance_constant en fixed_annuity")

        term_days = _original_term_days(start_date, maturity_date)
        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = _lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_maturity))
            renew_rate = rf + renewal_margin
            total += _project_fixed_annuity_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                cycle_maturity=cycle_maturity,
                outstanding=outstanding,
                sign=sign,
                base=base,
                fixed_rate=renew_rate,
                payment_frequency=payment_frequency,
            )
            cycle_start = cycle_maturity

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
    NII 12m para variable_annuity.

    Modo de cuota (configurable):
    - reprice_on_reset (default/legacy): recalcula la cuota en cada reset.
    - fixed_payment: mantiene cuota fija desde inicio de ciclo.

    Si existe columna `annuity_payment_mode` por contrato, prevalece sobre
    el parametro global.
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _VARIABLE_ANNUITY_REQUIRED_COLUMNS, "variable_annuity")
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    # Compatibilidad hacia atras: si no se configura nada, mantenemos
    # exactamente el comportamiento historico (reprice_on_reset).
    global_annuity_payment_mode = _normalise_annuity_payment_mode(
        annuity_payment_mode,
        row_id="<global>",
        field_name="annuity_payment_mode",
    )
    total = 0.0

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _VARIABLE_ANNUITY_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        outstanding = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        sign = _side_sign(row.side, row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))
        payment_frequency = _payment_frequency_or_default(row, row_id=row_id)

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = _coerce_float(row.spread, field_name="spread", row_id=row_id)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = (
            None
            if _is_blank(getattr(row, "fixed_rate", None))
            else _coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)
        )

        anchor_date = None
        if "next_reprice_date" in positions.columns and not _is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = _coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in positions.columns:
            frequency = _parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        row_annuity_payment_mode = global_annuity_payment_mode
        if "annuity_payment_mode" in positions.columns and not _is_blank(getattr(row, "annuity_payment_mode", None)):
            # Override por contrato para bancos/productos con mezcla de reglas.
            row_annuity_payment_mode = _normalise_annuity_payment_mode(
                getattr(row, "annuity_payment_mode", None),
                row_id=row_id,
            )

        total += _project_variable_annuity_cycle(
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

        renewal_spread = _lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        term_days = _original_term_days(start_date, maturity_date)
        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = _add_frequency(cycle_start, frequency)

            total += _project_variable_annuity_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                cycle_maturity=cycle_maturity,
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
            cycle_start = cycle_maturity

    return float(total)


def _prepare_scheduled_principal_flows(
    principal_flows: pd.DataFrame | None,
) -> dict[str, list[tuple[date, float]]]:
    if principal_flows is None:
        raise ValueError(
            "principal_flows es obligatorio para proyectar source_contract_type scheduled."
        )
    if principal_flows.empty:
        return {}

    required = ("contract_id", "flow_date", "principal_amount")
    missing = [c for c in required if c not in principal_flows.columns]
    if missing:
        raise ValueError(f"principal_flows sin columnas requeridas: {missing}")

    pf = principal_flows.copy()
    pf["contract_id"] = pf["contract_id"].astype("string").str.strip()
    invalid_id = pf["contract_id"].isna() | pf["contract_id"].eq("")
    if invalid_id.any():
        rows = [int(i) + 2 for i in pf.index[invalid_id][:10].tolist()]
        raise ValueError(f"principal_flows con contract_id vacio en filas {rows}")

    parsed_dates = pd.to_datetime(pf["flow_date"], errors="coerce").dt.date
    invalid_date = parsed_dates.isna()
    if invalid_date.any():
        rows = [int(i) + 2 for i in pf.index[invalid_date][:10].tolist()]
        raise ValueError(f"principal_flows con flow_date invalida en filas {rows}")
    pf["flow_date"] = parsed_dates

    parsed_amount = pd.to_numeric(pf["principal_amount"], errors="coerce")
    invalid_amount = parsed_amount.isna()
    if invalid_amount.any():
        rows = [int(i) + 2 for i in pf.index[invalid_amount][:10].tolist()]
        raise ValueError(f"principal_flows con principal_amount invalido en filas {rows}")
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


def _scheduled_flow_map_for_window(
    contract_flows: list[tuple[date, float]],
    *,
    cycle_start: date,
    cycle_end: date,
) -> dict[date, float]:
    """Filtra flujos de principal en el intervalo semiabierto (cycle_start, cycle_end].

    Los flujos en cycle_start se excluyen porque representan amortizaciones ya
    ocurridas cuyo efecto ya esta reflejado en el saldo vivo (outstanding) de
    entrada.  Los flujos en cycle_end se incluyen para capturar la devolucion
    a vencimiento.  Esta convencion es estandar en motores de cashflow.
    """
    out: dict[date, float] = {}
    if cycle_end <= cycle_start:
        return out
    for flow_date, amount in contract_flows:
        if flow_date <= cycle_start or flow_date > cycle_end:
            continue
        out[flow_date] = out.get(flow_date, 0.0) + float(amount)
    return out


def _apply_principal_flow(balance: float, principal_amount: float) -> float:
    out = float(balance) - float(principal_amount)
    if out < 0.0:
        return 0.0
    return out


def _scheduled_template_from_remaining_flows(
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


def _template_term_days(template: list[tuple[int, float]]) -> int:
    if not template:
        return 1
    return max(1, max(int(d) for d, _ in template))


def _scheduled_flow_map_from_template(
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


def _project_fixed_scheduled_cycle(
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

    # Flujos de principal en (cycle_start, cycle_end] — convencion semiabierta
    # coherente con _scheduled_flow_map_for_window.
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

        # Interes devengado sobre el balance vivo durante el segmento.
        # El principal se aplica al final del segmento, tras acumular interes.
        out += sign * balance * float(fixed_rate) * yearfrac(seg_start, seg_end, base)
        principal_at_end = float(principal_flow_map.get(seg_end, 0.0))
        if principal_at_end != 0.0:
            balance = _apply_principal_flow(balance, principal_at_end)
        if balance <= 1e-10:
            break

    return float(out)


def _project_variable_scheduled_cycle(
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

    reset_dates = _build_reset_dates(
        accrual_start=cycle_start,
        accrual_end=cycle_end,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    first_reset_after = _first_reset_after_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )
    reset_at_start = _reset_occurs_on_accrual_start(
        accrual_start=cycle_start,
        anchor_date=anchor_date,
        frequency=frequency,
    )

    # Flujos de principal en (cycle_start, cycle_end] — convencion semiabierta
    # coherente con _scheduled_flow_map_for_window.
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
        seg_rate = _apply_floor_cap(seg_rate, floor_rate=floor_rate, cap_rate=cap_rate)

        # Interes devengado sobre el balance vivo durante el segmento.
        # El principal se aplica al final del segmento, tras acumular interes.
        out += sign * balance * seg_rate * yearfrac(seg_start, seg_end, base)

        principal_at_end = float(principal_flow_map.get(seg_end, 0.0))
        if principal_at_end != 0.0:
            balance = _apply_principal_flow(balance, principal_at_end)
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
    NII 12m para fixed_scheduled usando flujos de principal explicitos.
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _FIXED_SCHEDULED_REQUIRED_COLUMNS, "fixed_scheduled")
    flows_by_contract = _prepare_scheduled_principal_flows(principal_flows)
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)

    total = 0.0
    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _FIXED_SCHEDULED_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        contract_flows = flows_by_contract.get(contract_id, [])

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        outstanding = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        fixed_rate = _coerce_float(row.fixed_rate, field_name="fixed_rate", row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))
        sign = _side_sign(row.side, row_id=row_id)

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        flow_map = _scheduled_flow_map_for_window(
            contract_flows,
            cycle_start=accrual_start,
            cycle_end=accrual_end,
        )
        total += _project_fixed_scheduled_cycle(
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
            raise ValueError("curve_set requerido para balance_constant en fixed_scheduled")

        benchmark_orig = maturity_date
        margin_default = fixed_rate - float(curve_set.rate_on_date(risk_free_index, benchmark_orig))
        renewal_margin = _lookup_margin_for_row(
            row=row,
            rate_type="fixed",
            margin_set=margin_set,
            default_margin=margin_default,
        )

        template = _scheduled_template_from_remaining_flows(
            contract_flows,
            accrual_start=accrual_start,
            maturity_date=maturity_date,
            outstanding=outstanding,
        )
        term_days = _template_term_days(template)

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            rf = float(curve_set.rate_on_date(risk_free_index, cycle_maturity))
            renew_rate = rf + renewal_margin

            flow_map = _scheduled_flow_map_from_template(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                template=template,
            )
            total += _project_fixed_scheduled_cycle(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                outstanding=outstanding,
                sign=sign,
                base=base,
                fixed_rate=renew_rate,
                principal_flow_map=flow_map,
            )
            cycle_start = cycle_maturity

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
    NII 12m para variable_scheduled usando flujos de principal explicitos.
    """
    if positions.empty:
        return 0.0
    _ensure_required_columns(positions, _VARIABLE_SCHEDULED_REQUIRED_COLUMNS, "variable_scheduled")
    flows_by_contract = _prepare_scheduled_principal_flows(principal_flows)
    horizon_end = _horizon_end(analysis_date, horizon_months=horizon_months)
    total = 0.0

    for row in positions.itertuples(index=False):
        row_id = getattr(row, "contract_id", "<missing>")
        for col in _VARIABLE_SCHEDULED_REQUIRED_COLUMNS:
            if _is_blank(getattr(row, col, None)):
                raise ValueError(f"Valor requerido vacio en {col!r} para contract_id={row_id!r}")

        contract_id = str(row.contract_id).strip()
        contract_flows = flows_by_contract.get(contract_id, [])

        start_date = _coerce_date(row.start_date, field_name="start_date", row_id=row_id)
        maturity_date = _coerce_date(row.maturity_date, field_name="maturity_date", row_id=row_id)
        if maturity_date < start_date:
            raise ValueError(f"maturity_date < start_date para contract_id={row_id!r}: {start_date} > {maturity_date}")

        accrual_start = max(start_date, analysis_date)
        accrual_end = min(maturity_date, horizon_end)
        if accrual_end <= accrual_start:
            continue

        outstanding = _coerce_float(row.notional, field_name="notional", row_id=row_id)
        sign = _side_sign(row.side, row_id=row_id)
        base = normalizar_base_de_calculo(str(row.daycount_base))

        index_name = str(row.index_name).strip()
        curve_set.get(index_name)
        spread = _coerce_float(row.spread, field_name="spread", row_id=row_id)
        floor_rate = getattr(row, "floor_rate", None)
        cap_rate = getattr(row, "cap_rate", None)
        fixed_rate_stub = (
            None
            if _is_blank(getattr(row, "fixed_rate", None))
            else _coerce_float(getattr(row, "fixed_rate", None), field_name="fixed_rate", row_id=row_id)
        )

        anchor_date = None
        if "next_reprice_date" in positions.columns and not _is_blank(getattr(row, "next_reprice_date", None)):
            anchor_date = _coerce_date(getattr(row, "next_reprice_date", None), field_name="next_reprice_date", row_id=row_id)
        frequency = None
        if "repricing_freq" in positions.columns:
            frequency = _parse_frequency_token(getattr(row, "repricing_freq", None), row_id=row_id)

        flow_map = _scheduled_flow_map_for_window(
            contract_flows,
            cycle_start=accrual_start,
            cycle_end=accrual_end,
        )
        total += _project_variable_scheduled_cycle(
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

        renewal_spread = _lookup_margin_for_row(
            row=row,
            rate_type="float",
            margin_set=margin_set,
            default_margin=spread,
        )
        template = _scheduled_template_from_remaining_flows(
            contract_flows,
            accrual_start=accrual_start,
            maturity_date=maturity_date,
            outstanding=outstanding,
        )
        term_days = _template_term_days(template)

        cycle_start = maturity_date
        while cycle_start < horizon_end:
            cycle_maturity = _cycle_maturity(cycle_start, term_days)
            cycle_end = min(cycle_maturity, horizon_end)
            renewal_anchor = None
            if frequency is not None:
                renewal_anchor = _add_frequency(cycle_start, frequency)

            flow_map = _scheduled_flow_map_from_template(
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                template=template,
            )
            total += _project_variable_scheduled_cycle(
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
            cycle_start = cycle_maturity

    return float(total)
