from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from math import exp, log
import pandas as pd


@dataclass(frozen=True)
class CurvePoint:
    year_frac: float      # T (años)
    rate: float           # r(T) en decimal (asumimos comp. continua para DF)
    tenor: str            # "ON", "1M", ...
    tenor_date: date      # fecha pilar (analysis_date + tenor)


@dataclass
class ForwardCurve:
    index_name: str
    points: list[CurvePoint]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError(f"Curva '{self.index_name}' sin puntos.")

        self.points.sort(key=lambda p: p.year_frac)

        # Validación: T estrictamente creciente
        prev = None
        for p in self.points:
            if prev is not None and p.year_frac <= prev:
                raise ValueError(
                    f"Curva '{self.index_name}' tiene YearFrac no estrictamente creciente "
                    f"(duplicado o desorden)."
                )
            prev = p.year_frac

    @property
    def year_fracs(self) -> list[float]:
        return [p.year_frac for p in self.points]

    @property
    def rates(self) -> list[float]:
        return [p.rate for p in self.points]

    # ---------- Nucleo: log-lineal en DF ----------
    def _pillar_ln_dfs(self) -> list[float]:
        # ln(DF_i) = -r_i * T_i (comp. continua)
        return [-p.rate * p.year_frac for p in self.points]

    @staticmethod
    def _interp_linear(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
        if x1 == x0:
            return y1
        w = (x - x0) / (x1 - x0)
        return y0 + w * (y1 - y0)

    def discount_factor(self, t: float) -> float:
        """
        DF(t) con interpolacion log-lineal en ln(DF):
        - Para 0 < t < primer pilar: interpola entre (0, lnDF=0) y primer pilar.
        - Entre pilares: interpolacion lineal en lnDF.
        - Para t > ultimo pilar: extrapolacion (no interpolacion), usando la
          pendiente del ultimo tramo en ln(DF).

        Nota de modelizacion para cola larga:
        - Esta extrapolacion implica "flat forward instantaneo" en cola
          (constante la pendiente de ln(DF)).
        - NO implica "flat zero rate".
        - Si se requiere otra cola (p.ej. convergencia a UFR), debe
          implementarse como modo alternativo explicito.
        """
        if t is None:
            raise ValueError("t no puede ser None.")
        t = float(t)

        if t <= 0.0:
            return 1.0

        xs = self.year_fracs
        ln_dfs = self._pillar_ln_dfs()

        if len(xs) == 1:
            x1 = xs[0]
            y1 = ln_dfs[0]
            if t <= x1:
                ln_df_t = self._interp_linear(t, 0.0, x1, 0.0, y1)
            else:
                ln_df_t = self._interp_linear(t, 0.0, x1, 0.0, y1)
            return exp(ln_df_t)

        if t <= xs[0]:
            ln_df_t = self._interp_linear(t, 0.0, xs[0], 0.0, ln_dfs[0])
            return exp(ln_df_t)

        if t >= xs[-1]:
            # Fuera del dominio de pilares: aqui no hay interpolacion posible.
            # Se extrapola linealmente ln(DF) con la pendiente del ultimo tramo.
            # Equivale a forward instantaneo constante en cola.
            ln_df_t = self._interp_linear(
                t,
                xs[-2],
                xs[-1],
                ln_dfs[-2],
                ln_dfs[-1],
            )
            return exp(ln_df_t)

        j = bisect_left(xs, t)
        ln_df_t = self._interp_linear(
            t,
            xs[j - 1],
            xs[j],
            ln_dfs[j - 1],
            ln_dfs[j],
        )
        return exp(ln_df_t)

    def zero_rate(self, t: float) -> float:
        """
        r(t) equivalente (comp continua) derivada de DF(t):
          r(t) = -ln DF(t) / t
        """
        t = float(t)
        if t <= 0.0:
            # no está definida en 0; devolvemos el primer pilar como convención
            return float(self.points[0].rate)

        df = self.discount_factor(t)
        return -log(df) / t

    # Conveniencia: si tú piensas “rate(t)” que sea el zero_rate equivalente
    def rate(self, t: float) -> float:
        return self.zero_rate(t)


def curve_from_long_df(
    df_long: pd.DataFrame,
    index_name: str,
    col_index: str = "IndexName",
    col_tenor: str = "Tenor",
    col_rate: str = "FwdRate",
    col_tenor_date: str = "TenorDate",
    col_year_frac: str = "YearFrac",
) -> ForwardCurve:
    required = [col_index, col_tenor, col_rate, col_tenor_date, col_year_frac]
    missing = [c for c in required if c not in df_long.columns]
    if missing:
        raise ValueError(f"df_long no tiene columnas requeridas: {missing}")

    sub = df_long[df_long[col_index] == index_name].copy()
    if sub.empty:
        raise ValueError(f"No hay puntos para IndexName='{index_name}'.")

    if sub[col_year_frac].isna().any():
        raise ValueError(f"Curva '{index_name}' tiene YearFrac nulo.")
    if sub[col_rate].isna().any():
        raise ValueError(f"Curva '{index_name}' tiene FwdRate nulo.")

    points: list[CurvePoint] = []
    for _, r in sub.iterrows():
        points.append(
            CurvePoint(
                year_frac=float(r[col_year_frac]),
                rate=float(r[col_rate]),
                tenor=str(r[col_tenor]).strip().upper(),
                tenor_date=r[col_tenor_date],
            )
        )

    return ForwardCurve(index_name=index_name, points=points)
