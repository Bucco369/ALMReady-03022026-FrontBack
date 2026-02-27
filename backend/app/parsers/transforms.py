"""Value normalization helpers used across parsers and filters."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
import unicodedata

import numpy as np
import pandas as pd

from app.config import POSITION_PREFIXES, SUBCATEGORY_ID_ALIASES
from app.schemas import BalanceSheetSummary
from engine.io._utils import norm_token as _engine_norm_token, parse_number as _engine_parse_number


def _norm_key(text: str) -> str:
    return str(text).strip().lower()


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text))
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.lower().strip()

    out: list[str] = []
    prev_dash = False
    for ch in normalized:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True

    return "".join(out).strip("-") or "unknown"


def _to_text(value: Any) -> str | None:
    """Normalise a value to a stripped string, or None if blank/NaN.

    Delegates to ``engine.io._utils.norm_token`` as the single source of truth.
    """
    return _engine_norm_token(value)


def _to_float(value: Any) -> float | None:
    """Parse a numeric value to float, or None if blank/NaN/unparseable.

    Delegates to ``engine.io._utils.parse_number`` as the single source of truth.
    """
    if value is None:
        return None
    return _engine_parse_number(value)


def _to_iso_date(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date().isoformat()

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    text = _to_text(value)
    if text is None:
        return None

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _serialize_value_for_json(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return _to_iso_date(value)

    if isinstance(value, np.generic):
        py_val = value.item()
        if isinstance(py_val, float) and np.isnan(py_val):
            return None
        return py_val

    if isinstance(value, float) and np.isnan(value):
        return None

    if isinstance(value, str):
        text = value.strip()
        return text if text != "" else None

    return value


def _normalize_side(lado_balance: str | None, sheet_name: str) -> str:
    raw = (lado_balance or "").strip().lower()
    if raw.startswith("asset"):
        return "asset"
    if raw.startswith("liability"):
        return "liability"
    if raw.startswith("equity"):
        return "equity"
    if raw.startswith("derivative"):
        return "derivative"

    if sheet_name.startswith("A_"):
        return "asset"
    if sheet_name.startswith("L_"):
        return "liability"
    if sheet_name.startswith("E_"):
        return "equity"
    if sheet_name.startswith("D_"):
        return "derivative"
    return "asset"


def _normalize_categoria_ui(categoria_ui: str | None, side: str) -> str:
    text = (categoria_ui or "").strip()
    if text:
        return text

    if side == "asset":
        return "Assets"
    if side == "liability":
        return "Liabilities"
    if side == "equity":
        return "Equity"
    return "Derivatives"


def _to_subcategory_id(subcategoria_ui: str | None, sheet_name: str) -> str:
    label = (subcategoria_ui or "").strip()
    if label:
        mapped = SUBCATEGORY_ID_ALIASES.get(label.lower())
        if mapped:
            return mapped
        return _slugify(label)

    cleaned_sheet = sheet_name
    for prefix in POSITION_PREFIXES:
        if cleaned_sheet.startswith(prefix):
            cleaned_sheet = cleaned_sheet[len(prefix):]
            break
    return _slugify(cleaned_sheet.replace("_", " "))


def _normalize_rate_type(tipo_tasa: str | None) -> str | None:
    raw = (tipo_tasa or "").strip().lower()
    if raw in {"fijo", "fixed"}:
        return "Fixed"
    if raw in {"variable", "floating", "float", "nonrate", "non-rate", "no-rate"}:
        return "Floating"
    return None



def _maturity_years(fecha_vencimiento: str | None, fallback_years: float | None) -> float | None:
    if fecha_vencimiento:
        try:
            venc = datetime.fromisoformat(fecha_vencimiento).date()
            now = datetime.now(timezone.utc).date()
            years = (venc - now).days / 365.25
            if years >= 0:
                return years
        except (ValueError, TypeError):
            pass

    if fallback_years is not None and fallback_years >= 0:
        return fallback_years

    return None


def _bucket_from_years(years: float | None) -> str | None:
    if years is None:
        return None
    if years < 1:
        return "<1Y"
    if years < 5:
        return "1-5Y"
    if years < 10:
        return "5-10Y"
    if years < 20:
        return "10-20Y"
    return ">20Y"


def _weighted_average(
    rows: list[dict[str, Any]], value_key: str, weight_key: str = "amount",
) -> float | None:
    weighted_sum = 0.0
    weight = 0.0

    for row in rows:
        w_raw = _to_float(row.get(weight_key)) or 0.0
        value = _to_float(row.get(value_key))
        if value is None or w_raw == 0:
            continue
        w = abs(w_raw)
        weighted_sum += value * w
        weight += w

    if weight == 0:
        return None
    return weighted_sum / weight


def _weighted_avg_rate(rows: list[dict[str, Any]]) -> float | None:
    return _weighted_average(rows, "rate_display")


def _weighted_avg_maturity(rows: list[dict[str, Any]]) -> float | None:
    return _weighted_average(rows, "maturity_years")


def _safe_sheet_summary(sheet_name: str, df: pd.DataFrame) -> BalanceSheetSummary:
    normalized_cols = {_norm_key(c): c for c in df.columns}

    saldo_col = normalized_cols.get("saldo_ini")
    saldo_total = None
    if saldo_col is not None:
        saldo_total = float(pd.to_numeric(df[saldo_col], errors="coerce").fillna(0).sum())

    book_col = normalized_cols.get("book_value")
    book_total = None
    if book_col is not None:
        book_total = float(pd.to_numeric(df[book_col], errors="coerce").fillna(0).sum())

    tae_col = normalized_cols.get("tae")
    avg_tae = None
    if tae_col is not None:
        s = pd.to_numeric(df[tae_col], errors="coerce")
        if s.notna().any():
            avg_tae = float(s.mean())

    return BalanceSheetSummary(
        sheet=sheet_name,
        rows=int(df.shape[0]),
        columns=[str(c) for c in df.columns],
        total_saldo_ini=saldo_total,
        total_book_value=book_total,
        avg_tae=avg_tae,
    )
