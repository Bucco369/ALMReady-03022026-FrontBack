from __future__ import annotations

from datetime import date


# --- Bases canónicas del motor ---
BASE_ACT_360 = "ACT/360"
BASE_ACT_365 = "ACT/365"
BASE_ACT_ACT = "ACT/ACT"
BASE_30_360  = "30/360"


# --- Mapeo de entradas típicas a bases canónicas ---
BASE_DE_CALCULO_MAP = {
    # ACT/360
    "ACT/360": BASE_ACT_360,
    "ACT360": BASE_ACT_360,
    "A/360": BASE_ACT_360,
    "ACTUAL/360": BASE_ACT_360,
    "ACTUAL/360.0": BASE_ACT_360,

    # ACT/365 (y variantes típicas)
    "ACT/365": BASE_ACT_365,
    "ACT365": BASE_ACT_365,
    "A/365": BASE_ACT_365,
    "ACTUAL/365": BASE_ACT_365,
    "ACTUAL/365F": BASE_ACT_365,
    "ACT/365F": BASE_ACT_365,

    # ACT/ACT
    "ACT/ACT": BASE_ACT_ACT,
    "ACTACT": BASE_ACT_ACT,
    "A/A": BASE_ACT_ACT,
    "ACTUAL/ACTUAL": BASE_ACT_ACT,
    "ACTUAL/ACT": BASE_ACT_ACT,
    "ACT/ACTISDA": BASE_ACT_ACT,
    "ACTUAL/ACTUALISDA": BASE_ACT_ACT,

    # 30/360
    "30/360": BASE_30_360,
    "30360": BASE_30_360,
    "30E/360": BASE_30_360,
    "30E360": BASE_30_360,
    "30E/360ISDA": BASE_30_360,
    "30E360ISDA": BASE_30_360,
}


def normalizar_base_de_calculo(valor: str) -> str:
    """
    Normaliza variantes a una base canónica del motor:
    ACT/360, ACT/365, ACT/ACT, 30/360
    """
    if valor is None:
        raise ValueError("Base de calculo vacía.")

    v = str(valor).strip().upper()

    # normalización básica
    v = v.replace(" ", "").replace("-", "/")

    # quita paréntesis típicos: 30/360(US) o 30/360(USNASD)
    for ch in ("(", ")", "[", "]"):
        v = v.replace(ch, "")

    # normaliza variantes comunes de notación 30E.
    v = v.replace("30/360E", "30E/360")

    # variantes frecuentes con sufijos
    v = v.replace("US", "")          # 30/360US
    v = v.replace("NASD", "")        # 30/360NASD
    v = v.replace("FIXED", "F")      # ACT/365FIXED -> ACT/365F

    if v in BASE_DE_CALCULO_MAP:
        return BASE_DE_CALCULO_MAP[v]

    raise ValueError(f"Base de calculo no reconocida: {valor!r}")


# ============================================================
# Helpers: bisiestos y fin de mes (para 30/360 US con febrero)
# ============================================================
def es_año_bisiesto(año: int) -> bool:
    return (año % 4 == 0 and año % 100 != 0) or (año % 400 == 0)


def _ultimo_dia_mes(año: int, mes: int) -> int:
    if mes == 2:
        return 29 if es_año_bisiesto(año) else 28
    if mes in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _es_ultimo_dia_mes(d: date) -> bool:
    return d.day == _ultimo_dia_mes(d.year, d.month)


def _es_ultimo_dia_febrero(d: date) -> bool:
    return d.month == 2 and _es_ultimo_dia_mes(d)


# ============================================================
# Year fraction
# ============================================================
def yearfrac(d0: date, d1: date, base: str) -> float:
    """
    Fracción de año entre d0 y d1 según base canónica:
      ACT/360, ACT/365, ACT/ACT (ISDA), 30/360 (US)
    """
    if d1 < d0:
        raise ValueError("d1 debe ser >= d0")

    days = (d1 - d0).days

    if base == BASE_ACT_360:
        return days / 360.0

    if base == BASE_ACT_365:
        return days / 365.0

    if base == BASE_ACT_ACT:
        return yearfrac_act_act_isda(d0, d1)

    if base == BASE_30_360:
        return yearfrac_30_360_us(d0, d1)

    raise ValueError(f"Base no soportada: {base}")


def yearfrac_act_act_isda(d0: date, d1: date) -> float:
    if d1 < d0:
        raise ValueError("d1 debe ser >= d0")
    if d0 == d1:
        return 0.0

    def diy(y: int) -> int:
        return 366 if es_año_bisiesto(y) else 365

    if d0.year == d1.year:
        return (d1 - d0).days / float(diy(d0.year))

    end_y0 = date(d0.year + 1, 1, 1)
    yf = (end_y0 - d0).days / float(diy(d0.year))

    yf += max(0, d1.year - d0.year - 1)

    start_y1 = date(d1.year, 1, 1)
    yf += (d1 - start_y1).days / float(diy(d1.year))

    return yf


def yearfrac_30_360_us(d0: date, d1: date) -> float:
    """
    30/360 (US) con ajuste especial de febrero (NASD).
    """
    if d1 < d0:
        raise ValueError("d1 debe ser >= d0")

    d0_day, d1_day = d0.day, d1.day
    d0_month, d1_month = d0.month, d1.month
    d0_year, d1_year = d0.year, d1.year

    # Ajuste especial: fin de febrero
    if _es_ultimo_dia_febrero(d0):
        d0_day = 30
    if _es_ultimo_dia_febrero(d1) and d0_day in (30, 31):
        d1_day = 30

    # Ajustes por 31
    if d0_day == 31:
        d0_day = 30
    if d1_day == 31 and d0_day in (30, 31):
        d1_day = 30

    days_360 = (
        360 * (d1_year - d0_year)
        + 30 * (d1_month - d0_month)
        + (d1_day - d0_day)
    )
    return days_360 / 360.0
