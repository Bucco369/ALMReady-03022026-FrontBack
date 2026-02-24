"""Curves parsing: tenor parsing, workbook parsing, forward curves, persistence."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException

from app.schemas import (
    CurveCatalogItem,
    CurvePoint,
    CurvePointsResponse,
    CurvesSummaryResponse,
)
from app.session import (
    _curves_points_path,
    _curves_summary_path,
    _latest_curves_file,
)
from app.parsers.transforms import _to_float, _to_text


_TENOR_TOKEN_RE = re.compile(r"^\s*(\d+)\s*([DWMY])\s*$", re.IGNORECASE)


def _tenor_to_years(tenor: str | None) -> float | None:
    if tenor is None:
        return None

    token = tenor.strip().upper()
    if token == "":
        return None

    if token == "ON":
        return 1.0 / 365.0

    match = _TENOR_TOKEN_RE.match(token)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2).upper()

    if unit == "D":
        return value / 365.0
    if unit == "W":
        return (7.0 * value) / 365.0
    if unit == "M":
        return value / 12.0
    if unit == "Y":
        return float(value)

    return None


def _extract_currency_from_curve_id(curve_id: str) -> str | None:
    token = curve_id.strip().upper()
    if "_" in token:
        prefix = token.split("_", 1)[0]
        if len(prefix) == 3 and prefix.isalpha():
            return prefix
    return None


def _parse_curves_workbook(xlsx_path: Path) -> tuple[list[CurveCatalogItem], dict[str, list[CurvePoint]], str | None]:
    try:
        xls = pd.ExcelFile(xlsx_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read curves Excel file: {exc}")

    if not xls.sheet_names:
        raise HTTPException(status_code=400, detail="Curves workbook has no sheets")

    selected_df: pd.DataFrame | None = None
    tenor_columns: list[tuple[str, str, float]] = []

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
        if df.empty or len(df.columns) < 2:
            continue

        candidate_tenors: list[tuple[str, str, float]] = []
        for raw_col in list(df.columns)[1:]:
            tenor = _to_text(raw_col)
            t_years = _tenor_to_years(tenor)
            if tenor is None or t_years is None:
                continue
            candidate_tenors.append((str(raw_col), tenor, t_years))

        if candidate_tenors:
            selected_df = df
            tenor_columns = candidate_tenors
            break

    if selected_df is None or not tenor_columns:
        raise HTTPException(
            status_code=400,
            detail="Could not find tenor columns in curves workbook (expected ON, 1W, 1M, 1Y, etc.)",
        )

    id_col = str(selected_df.columns[0])
    records = selected_df.to_dict(orient="records")

    points_by_curve: dict[str, list[CurvePoint]] = {}
    catalog: list[CurveCatalogItem] = []

    for row in records:
        curve_id = _to_text(row.get(id_col))
        if curve_id is None:
            continue

        points: list[CurvePoint] = []
        for raw_col, tenor, t_years in tenor_columns:
            rate = _to_float(row.get(raw_col))
            if rate is None:
                continue
            points.append(CurvePoint(tenor=tenor, t_years=float(t_years), rate=float(rate)))

        points = sorted(points, key=lambda p: p.t_years)
        if not points:
            continue

        points_by_curve[curve_id] = points
        catalog.append(
            CurveCatalogItem(
                curve_id=curve_id,
                currency=_extract_currency_from_curve_id(curve_id),
                label_tech=curve_id,
                points_count=len(points),
                min_t=points[0].t_years,
                max_t=points[-1].t_years,
            )
        )

    if not catalog:
        raise HTTPException(status_code=400, detail="No valid curve rows found in workbook")

    default_curve_id = "EUR_ESTR_OIS" if "EUR_ESTR_OIS" in points_by_curve else catalog[0].curve_id

    return catalog, points_by_curve, default_curve_id


def _persist_curves_payload(
    session_id: str,
    response: CurvesSummaryResponse,
    points_by_curve: dict[str, list[CurvePoint]],
) -> None:
    _curves_summary_path(session_id).write_text(response.model_dump_json(indent=2), encoding="utf-8")

    payload = {
        curve_id: [point.model_dump() for point in points]
        for curve_id, points in points_by_curve.items()
    }
    _curves_points_path(session_id).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_and_store_curves(session_id: str, filename: str, xlsx_path: Path) -> CurvesSummaryResponse:
    catalog, points_by_curve, default_curve_id = _parse_curves_workbook(xlsx_path)

    response = CurvesSummaryResponse(
        session_id=session_id,
        filename=filename,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        default_discount_curve_id=default_curve_id,
        curves=catalog,
    )
    _persist_curves_payload(session_id, response, points_by_curve)
    return response


def _load_or_rebuild_curves_summary(session_id: str) -> CurvesSummaryResponse:
    summary_file = _curves_summary_path(session_id)
    points_file = _curves_points_path(session_id)
    if summary_file.exists() and points_file.exists():
        payload = json.loads(summary_file.read_text(encoding="utf-8"))
        return CurvesSummaryResponse(**payload)

    xlsx_path = _latest_curves_file(session_id)
    filename = xlsx_path.name.removeprefix("curves__")
    return _parse_and_store_curves(session_id, filename=filename, xlsx_path=xlsx_path)


def _load_or_rebuild_curve_points(session_id: str) -> dict[str, list[CurvePoint]]:
    points_file = _curves_points_path(session_id)
    if points_file.exists():
        payload = json.loads(points_file.read_text(encoding="utf-8"))
        return {
            curve_id: [CurvePoint(**point) for point in points]
            for curve_id, points in payload.items()
        }

    _load_or_rebuild_curves_summary(session_id)
    if not points_file.exists():
        raise HTTPException(status_code=404, detail="No curves uploaded for this session yet")

    payload = json.loads(points_file.read_text(encoding="utf-8"))
    return {
        curve_id: [CurvePoint(**point) for point in points]
        for curve_id, points in payload.items()
    }


def _build_forward_curve_set(
    session_id: str,
    analysis_date: date,
    curve_base: str = "ACT/365",
) -> Any:
    from engine.core.curves import curve_from_long_df
    from engine.core.tenors import add_tenor
    from engine.services.market import ForwardCurveSet as MotorForwardCurveSet

    points_by_curve = _load_or_rebuild_curve_points(session_id)
    if not points_by_curve:
        raise HTTPException(status_code=404, detail="No curves uploaded for this session yet")

    rows: list[dict[str, Any]] = []
    for curve_id, points in points_by_curve.items():
        for pt in points:
            try:
                tenor_date = add_tenor(analysis_date, pt.tenor)
            except Exception:
                from datetime import timedelta
                tenor_date = analysis_date + timedelta(days=round(pt.t_years * 365.25))

            rows.append({
                "IndexName": curve_id,
                "Tenor": pt.tenor,
                "FwdRate": pt.rate,
                "TenorDate": tenor_date,
                "YearFrac": pt.t_years,
            })

    df_long = pd.DataFrame(rows)

    index_names = sorted(df_long["IndexName"].unique().tolist())
    curves = {}
    for ix in index_names:
        curves[ix] = curve_from_long_df(df_long, ix)

    return MotorForwardCurveSet(
        analysis_date=analysis_date,
        base=curve_base,
        points=df_long,
        curves=curves,
    )
