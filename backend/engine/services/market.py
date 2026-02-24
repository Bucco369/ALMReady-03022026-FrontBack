from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, Union

import pandas as pd

from engine.io.curves_forward_reader import load_forward_curves
from engine.core.curves import ForwardCurve, curve_from_long_df
from engine.core.daycount import normalizar_base_de_calculo, yearfrac


@dataclass
class ForwardCurveSet:
    """
    Set de curvas forward por IndexName, ya listo para consultar rates/DF.
    """
    analysis_date: date
    base: str
    points: pd.DataFrame               # tabla long canónica (debug/export)
    curves: Dict[str, ForwardCurve]    # index_name -> ForwardCurve

    @property
    def available_indices(self) -> list[str]:
        return sorted(self.curves.keys())

    def get(self, index_name: str) -> ForwardCurve:
        if index_name not in self.curves:
            available = self.available_indices
            raise KeyError(f"Curva no encontrada: {index_name!r}. Disponibles: {available}")
        return self.curves[index_name]

    def require_indices(self, required_indices: Iterable[str]) -> None:
        """
        Falla si falta cualquier indice requerido en el set de curvas.
        """
        required = sorted(
            {
                str(ix).strip()
                for ix in required_indices
                if ix is not None and str(ix).strip() != ""
            }
        )
        missing = [ix for ix in required if ix not in self.curves]
        if missing:
            raise KeyError(
                f"Faltan curvas para indices requeridos: {missing}. "
                f"Disponibles: {self.available_indices}"
            )

    def require_float_index_coverage(
        self,
        positions: pd.DataFrame,
        *,
        rate_type_col: str = "rate_type",
        index_col: str = "index_name",
        row_offset: int = 2,
    ) -> None:
        """
        Garantiza cobertura de curvas para posiciones flotantes.
        """
        for col in (rate_type_col, index_col):
            if col not in positions.columns:
                raise ValueError(f"positions no contiene columna requerida: {col!r}")

        rate_tokens = (
            positions[rate_type_col]
            .astype("string")
            .str.strip()
            .str.lower()
        )
        float_mask = rate_tokens.eq("float")
        if not float_mask.any():
            return

        missing_index_mask = (
            float_mask
            & (
                positions[index_col].isna()
                | positions[index_col].astype("string").str.strip().eq("")
            )
        )
        if missing_index_mask.any():
            rows = [int(i) + row_offset for i in positions.index[missing_index_mask][:10]]
            raise ValueError(
                f"Posiciones float sin index_name en filas {rows}"
            )

        required = (
            positions.loc[float_mask, index_col]
            .astype("string")
            .str.strip()
            .dropna()
            .tolist()
        )
        self.require_indices(required)

    def _t(self, d: date) -> float:
        """
        Convierte una fecha calendario a year-fraction desde analysis_date usando self.base.
        """
        b = normalizar_base_de_calculo(self.base)
        return yearfrac(self.analysis_date, d, b)

    def rate_on_date(self, index_name: str, d: date) -> float:
        """
        Tipo equivalente (comp. continua, vía DF log-lineal) en una fecha d.
        """
        curve = self.get(index_name)
        t = self._t(d)
        return curve.rate(t)

    def df_on_date(self, index_name: str, d: date) -> float:
        """
        Discount Factor en una fecha d (útil para EVE).
        """
        curve = self.get(index_name)
        t = self._t(d)
        return curve.discount_factor(t)


def load_forward_curve_set(
    path: str,
    analysis_date: date,
    base: str = "ACT/365",
    sheet_name: Union[int, str] = 0,
) -> ForwardCurveSet:
    """
    Pipeline:
      Excel curvas (wide) -> long canónico -> ForwardCurve por IndexName
    """
    df = load_forward_curves(
        path,
        analysis_date=analysis_date,
        base=base,
        sheet_name=sheet_name,
    )

    index_names = sorted(df["IndexName"].unique().tolist())
    curves: Dict[str, ForwardCurve] = {}
    for ix in index_names:
        curves[ix] = curve_from_long_df(df, ix)

    return ForwardCurveSet(
        analysis_date=analysis_date,
        base=base,
        points=df,
        curves=curves,
    )
