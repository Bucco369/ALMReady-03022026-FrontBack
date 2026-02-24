"""Frequency token parsing and tenor arithmetic."""

from __future__ import annotations

import re
from datetime import date

from dateutil.relativedelta import relativedelta


def parse_frequency_token(
    value: object,
    *,
    strict: bool = False,
    row_id: object = None,
    field_name: str = "repricing_freq",
) -> tuple[int, str] | None:
    """Parse a frequency token like '3M', '6M', 'ON' into (count, unit).

    Parameters
    ----------
    value : object
        Raw frequency value (e.g. "3M", "12M", "ON").
    strict : bool
        If True, raise ValueError on unparseable input.
        If False, return None.
    row_id, field_name : object
        Context for error messages when *strict* is True.

    Returns
    -------
    tuple[int, str] | None
        (count, unit) where unit is 'D', 'W', 'M', or 'Y'; or None if blank/zero.
    """
    if value is None:
        return None
    if isinstance(value, float) and (value != value):  # NaN
        return None
    if isinstance(value, str) and value.strip() == "":
        return None

    token = str(value).strip().upper().replace(" ", "")
    if token in {"0D", "0W", "0M", "0Y"}:
        return None
    if token in {"ON", "O/N"}:
        return (1, "D")

    m = re.match(r"^(\d+)([DWMY])$", token)
    if not m:
        if strict:
            raise ValueError(
                f"Frecuencia invalida en {field_name!r} para contract_id={row_id!r}: {value!r}"
            )
        return None

    n = int(m.group(1))
    unit = m.group(2)
    if n <= 0:
        return None
    return (n, unit)


def add_frequency(d: date, frequency: tuple[int, str]) -> date:
    """Add a parsed frequency (count, unit) to a date."""
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
