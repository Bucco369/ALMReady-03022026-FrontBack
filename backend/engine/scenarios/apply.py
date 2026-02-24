from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from engine.scenarios._curve_utils import (
    rebuild_curves as _rebuild_curves,
    validate_curve_points_columns as _validate_curve_points_columns,
)
from engine.scenarios.shocks import ParallelShock
from engine.services.market import ForwardCurveSet


def _normalise_apply_to(
    apply_to: Iterable[str] | None,
    available_indexes: set[str],
) -> set[str]:
    if apply_to is None:
        return set(available_indexes)

    selected = {str(ix).strip() for ix in apply_to if str(ix).strip() != ""}
    if not selected:
        raise ValueError("apply_to se ha informado pero no contiene indices validos.")

    unknown = sorted(selected - available_indexes)
    if unknown:
        available = sorted(available_indexes)
        raise ValueError(f"Indices no encontrados en base_set: {unknown}. Disponibles: {available}")

    return selected


def apply_parallel_shock(
    base_set: ForwardCurveSet,
    shock: ParallelShock,
    apply_to: Iterable[str] | None = None,
) -> ForwardCurveSet:
    """
    Aplica un shift paralelo (en bps) sobre FwdRate y devuelve un nuevo ForwardCurveSet.

    - `apply_to=None`: aplica a todos los indices.
    - `apply_to=[...]`: aplica solo al subset indicado.
    """

    _validate_curve_points_columns(base_set.points)

    df_shifted = base_set.points.copy(deep=True)
    available_indexes = set(df_shifted["IndexName"].astype(str).unique().tolist())
    selected_indexes = _normalise_apply_to(apply_to, available_indexes)

    mask = df_shifted["IndexName"].astype(str).isin(selected_indexes)
    df_shifted.loc[mask, "FwdRate"] = df_shifted.loc[mask, "FwdRate"].astype(float) + shock.shift_decimal

    shifted_curves = _rebuild_curves(df_shifted)

    return ForwardCurveSet(
        analysis_date=base_set.analysis_date,
        base=base_set.base,
        points=df_shifted,
        curves=shifted_curves,
    )


def apply_parallel_shocks(
    base_set: ForwardCurveSet,
    shocks: Iterable[ParallelShock],
    apply_to: Iterable[str] | None = None,
) -> dict[str, ForwardCurveSet]:
    """
    Ejecuta varios shocks paralelos y devuelve un diccionario escenario -> ForwardCurveSet.
    """

    out: dict[str, ForwardCurveSet] = {}
    for shock in shocks:
        if shock.name in out:
            raise ValueError(f"Nombre de escenario duplicado: {shock.name!r}")
        out[shock.name] = apply_parallel_shock(base_set, shock=shock, apply_to=apply_to)
    return out

