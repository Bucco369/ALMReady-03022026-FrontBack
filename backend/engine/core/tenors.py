from __future__ import annotations

from datetime import date
from dateutil.relativedelta import relativedelta


def add_tenor(d: date, tenor: str) -> date:
    """
    Suma un tenor tipo 'ON', '1W', '3M', '5Y' a una fecha d.

    Nota: NO aplica ajuste de calendario hábil (business day adjustment).
    """
    t = str(tenor).strip().upper()

    if t in ("ON", "O/N", "1D"):
        return d + relativedelta(days=1)

    if t.endswith("W"):
        n = int(t[:-1])
        return d + relativedelta(weeks=n)

    if t.endswith("M"):
        n = int(t[:-1])
        return d + relativedelta(months=n)

    if t.endswith("Y"):
        n = int(t[:-1])
        return d + relativedelta(years=n)

    raise ValueError(f"Tenor no soportado: {tenor!r}")
