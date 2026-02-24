from __future__ import annotations

from datetime import date
from typing import Optional, Union

import pandas as pd

from engine.core.tenors import add_tenor
from engine.core.daycount import normalizar_base_de_calculo, yearfrac


def _parse_rate(x) -> Optional[float]:
    """
    Convierte rates que vengan como:
      - número (0.03)
      - string '0.03'
      - porcentaje '3.25%' o '3,25%'
    Devuelve float en formato decimal (0.0325).
    """
    if pd.isna(x):
        return None

    s = str(x).strip()
    if s == "":
        return None

    is_pct = "%" in s
    s = s.replace("%", "").replace(" ", "").replace(",", ".")

    try:
        v = float(s)
    except ValueError:
        return None

    if is_pct:
        v = v / 100.0

    return v


def read_forward_curves_wide(
    path: str,
    sheet_name: Union[int, str] = 0,
) -> pd.DataFrame:
    """
    Lee el Excel de curvas en formato WIDE:
      Col A: IndexName (desde fila 2 hacia abajo)
      Col B..: tenores (headers 1M, 3M, 1Y...)
      Celdas: forward rate

    Devuelve un DataFrame con columna 'IndexName' + columnas tenor.
    """
    df = pd.read_excel(path, sheet_name=sheet_name, header=0, engine="openpyxl")
    df = df.dropna(how="all")

    if df.shape[1] < 2:
        raise ValueError(
            "Formato inesperado: se esperaba 1a columna = índices y columnas B.. = tenores."
        )

    first_col = df.columns[0]
    df = df.rename(columns={first_col: "IndexName"})

    # Limpieza básica
    df["IndexName"] = df["IndexName"].astype(str).str.strip()
    df = df[df["IndexName"].notna() & (df["IndexName"] != "")]

    # Quita columnas basura típicas ("Unnamed: ...") si existieran
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed:")]

    return df


def wide_to_long(df_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte WIDE -> LONG:
      IndexName | Tenor | FwdRate
    """
    if "IndexName" not in df_wide.columns:
        raise ValueError("Falta columna 'IndexName' en df_wide.")

    tenor_cols = list(df_wide.columns[1:])
    if not tenor_cols:
        raise ValueError("No hay columnas de tenores (B..end).")

    df_long = df_wide.melt(
        id_vars=["IndexName"],
        value_vars=tenor_cols,
        var_name="Tenor",
        value_name="FwdRate_raw",
    )

    df_long["Tenor"] = df_long["Tenor"].astype(str).str.strip().str.upper()
    df_long["FwdRate"] = df_long["FwdRate_raw"].apply(_parse_rate)

    df_long = df_long.drop(columns=["FwdRate_raw"])
    df_long = df_long[df_long["FwdRate"].notna()]
    df_long = df_long[df_long["Tenor"].notna() & (df_long["Tenor"] != "")]

    return df_long.reset_index(drop=True)


def enrich_with_dates(
    df_long: pd.DataFrame,
    analysis_date: date,
    base: str = "ACT/365",
) -> pd.DataFrame:
    """
    Añade:
      - TenorDate = analysis_date + Tenor
      - YearFrac = yearfrac(analysis_date, TenorDate, base_normalizada)

    Valida tenores: si hay alguno no soportado, falla con error claro.
    """
    if df_long.empty:
        raise ValueError("df_long está vacío: no hay puntos de curva (rates) que procesar.")

    b = normalizar_base_de_calculo(base)

    tenores_unicos = sorted(df_long["Tenor"].unique().tolist())
    tenores_invalidos = []
    for t in tenores_unicos:
        try:
            add_tenor(analysis_date, t)
        except Exception:
            tenores_invalidos.append(t)

    if tenores_invalidos:
        raise ValueError(f"Tenores no soportados encontrados en el Excel: {tenores_invalidos}")

    df_long = df_long.copy()
    df_long["TenorDate"] = df_long["Tenor"].apply(lambda t: add_tenor(analysis_date, t))
    df_long["YearFrac"] = df_long["TenorDate"].apply(lambda d: yearfrac(analysis_date, d, b))
    return df_long


def load_forward_curves(
    path: str,
    analysis_date: date,
    base: str = "ACT/365",
    sheet_name: Union[int, str] = 0,
) -> pd.DataFrame:
    """
    Pipeline completo:
      Excel (wide) -> long -> con fechas y yearfrac
    """
    df_wide = read_forward_curves_wide(path, sheet_name=sheet_name)
    df_long = wide_to_long(df_wide)
    df_final = enrich_with_dates(df_long, analysis_date, base=base)
    return df_final
