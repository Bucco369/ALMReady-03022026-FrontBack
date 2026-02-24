"""Shared curve validation and rebuilding helpers for scenario modules."""

from __future__ import annotations

import pandas as pd

from engine.core.curves import ForwardCurve, curve_from_long_df


def validate_curve_points_columns(df_points: pd.DataFrame) -> None:
    """Raise ValueError if *df_points* lacks the columns needed for curve rebuilding."""
    required = ["IndexName", "Tenor", "FwdRate", "TenorDate", "YearFrac"]
    missing = [c for c in required if c not in df_points.columns]
    if missing:
        raise ValueError(
            "ForwardCurveSet.points no contiene columnas requeridas: "
            f"{missing}"
        )


def rebuild_curves(df_points: pd.DataFrame) -> dict[str, ForwardCurve]:
    """Rebuild a dict of ForwardCurve objects from a points DataFrame."""
    indexes = sorted(df_points["IndexName"].astype(str).unique().tolist())
    curves: dict[str, ForwardCurve] = {}
    for index_name in indexes:
        curves[index_name] = curve_from_long_df(df_points, index_name=index_name)
    return curves
