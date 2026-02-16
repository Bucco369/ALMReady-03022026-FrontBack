from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import json
import re
import unicodedata
import uuid

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI()

# CORS (dev): allow local frontend origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# API Models
# -------------------------
class SessionMeta(BaseModel):
    session_id: str
    created_at: str
    status: str = "active"
    schema_version: str = "v1"


class BalanceSheetSummary(BaseModel):
    sheet: str
    rows: int
    columns: list[str]
    total_saldo_ini: float | None = None
    total_book_value: float | None = None
    avg_tae: float | None = None


class BalanceTreeNode(BaseModel):
    id: str
    label: str
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None


class BalanceTreeCategory(BaseModel):
    id: str
    label: str
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None
    subcategories: list[BalanceTreeNode] = Field(default_factory=list)


class BalanceSummaryTree(BaseModel):
    assets: BalanceTreeCategory | None = None
    liabilities: BalanceTreeCategory | None = None
    equity: BalanceTreeCategory | None = None
    derivatives: BalanceTreeCategory | None = None


class BalanceUploadResponse(BaseModel):
    session_id: str
    filename: str
    uploaded_at: str
    sheets: list[BalanceSheetSummary]
    sample_rows: dict[str, list[dict[str, Any]]]
    summary_tree: BalanceSummaryTree


class BalanceContract(BaseModel):
    contract_id: str
    sheet: str | None = None
    category: str
    categoria_ui: str | None = None
    subcategory: str
    subcategoria_ui: str | None = None
    group: str | None = None
    currency: str | None = None
    counterparty: str | None = None
    rate_type: str | None = None
    maturity_bucket: str | None = None
    maturity_years: float | None = None
    amount: float | None = None
    rate: float | None = None


class BalanceContractsResponse(BaseModel):
    session_id: str
    total: int
    page: int
    page_size: int
    contracts: list[BalanceContract]


class FacetOption(BaseModel):
    value: str
    count: int


class BalanceDetailsFacets(BaseModel):
    currencies: list[FacetOption] = Field(default_factory=list)
    rate_types: list[FacetOption] = Field(default_factory=list)
    counterparties: list[FacetOption] = Field(default_factory=list)
    maturities: list[FacetOption] = Field(default_factory=list)


class BalanceDetailsGroup(BaseModel):
    group: str
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None


class BalanceDetailsTotals(BaseModel):
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None


class BalanceDetailsResponse(BaseModel):
    session_id: str
    categoria_ui: str | None = None
    subcategoria_ui: str | None = None
    groups: list[BalanceDetailsGroup]
    totals: BalanceDetailsTotals
    facets: BalanceDetailsFacets


class CurvePoint(BaseModel):
    tenor: str
    t_years: float
    rate: float


class CurveCatalogItem(BaseModel):
    curve_id: str
    currency: str | None = None
    label_tech: str
    points_count: int
    min_t: float | None = None
    max_t: float | None = None


class CurvesSummaryResponse(BaseModel):
    session_id: str
    filename: str
    uploaded_at: str
    default_discount_curve_id: str | None = None
    curves: list[CurveCatalogItem] = Field(default_factory=list)


class CurvePointsResponse(BaseModel):
    session_id: str
    curve_id: str
    points: list[CurvePoint]


# -------------------------
# In-memory and disk stores
# -------------------------
_SESSIONS: dict[str, SessionMeta] = {}

BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "data" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

META_SHEETS = {
    "README",
    "SCHEMA_BASE",
    "SCHEMA_DERIV",
    "BALANCE_CHECK",
    "BALANCE_SUMMARY",
    "CURVES_ENUMS",
}
POSITION_PREFIXES = ("A_", "L_", "E_", "D_")

BASE_REQUIRED_COLS = {
    "num_sec_ac",
    "lado_balance",
    "categoria_ui",
    "subcategoria_ui",
    "grupo",
    "moneda",
    "saldo_ini",
    "tipo_tasa",
}

SUBCATEGORY_ID_ALIASES = {
    "mortgages": "mortgages",
    "loans": "loans",
    "securities": "securities",
    "interbank / central bank": "interbank",
    "other assets": "other-assets",
    "deposits": "deposits",
    "term deposits": "term-deposits",
    "wholesale funding": "wholesale-funding",
    "debt issued": "debt-issued",
    "other liabilities": "other-liabilities",
    "equity": "equity",
}

ASSET_SUBCATEGORY_ORDER = [
    "mortgages",
    "loans",
    "securities",
    "interbank",
    "other-assets",
]
LIABILITY_SUBCATEGORY_ORDER = [
    "deposits",
    "term-deposits",
    "wholesale-funding",
    "debt-issued",
    "other-liabilities",
]


# -------------------------
# Path helpers
# -------------------------
def _session_dir(session_id: str) -> Path:
    path = SESSIONS_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_meta_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id / "meta.json"


def _positions_path(session_id: str) -> Path:
    return _session_dir(session_id) / "balance_positions.json"


def _summary_path(session_id: str) -> Path:
    return _session_dir(session_id) / "balance_summary.json"


def _curves_summary_path(session_id: str) -> Path:
    return _session_dir(session_id) / "curves_summary.json"


def _curves_points_path(session_id: str) -> Path:
    return _session_dir(session_id) / "curves_points.json"


def _latest_balance_file(session_id: str) -> Path:
    sdir = _session_dir(session_id)
    preferred = sorted(
        [
            p
            for p in sdir.iterdir()
            if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"} and p.name.startswith("balance__")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if preferred:
        return preferred[0]

    candidates = sorted(
        [
            p
            for p in sdir.iterdir()
            if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"} and not p.name.startswith("curves__")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="No balance uploaded for this session yet")
    return candidates[0]


def _latest_curves_file(session_id: str) -> Path:
    sdir = _session_dir(session_id)
    candidates = sorted(
        [
            p
            for p in sdir.iterdir()
            if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"} and p.name.startswith("curves__")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="No curves uploaded for this session yet")
    return candidates[0]


# -------------------------
# Session persistence helpers
# -------------------------
def _persist_session_meta(meta: SessionMeta) -> None:
    # Ensure session directory exists before persisting metadata.
    _session_dir(meta.session_id)
    _session_meta_path(meta.session_id).write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def _load_session_from_disk(session_id: str) -> SessionMeta | None:
    path = _session_meta_path(session_id)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = SessionMeta(**payload)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Corrupted session metadata for {session_id}: {exc}")

    _SESSIONS[session_id] = meta
    return meta


def _get_session_meta(session_id: str) -> SessionMeta | None:
    if session_id in _SESSIONS:
        return _SESSIONS[session_id]
    return _load_session_from_disk(session_id)


def _assert_session_exists(session_id: str) -> None:
    if _get_session_meta(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found. Create it first via POST /api/sessions")


# -------------------------
# Value normalization helpers
# -------------------------
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
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None

    text = str(value).strip()
    return text if text != "" else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if np.isnan(number):
        return None
    return number


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

    # fallback to sheet name without prefix
    cleaned_sheet = sheet_name
    for prefix in POSITION_PREFIXES:
        if cleaned_sheet.startswith(prefix):
            cleaned_sheet = cleaned_sheet[len(prefix) :]
            break
    return _slugify(cleaned_sheet.replace("_", " "))


def _normalize_rate_type(tipo_tasa: str | None) -> str | None:
    raw = (tipo_tasa or "").strip().lower()
    if raw in {"fijo", "fixed"}:
        return "Fixed"
    if raw in {"variable", "floating", "float", "nonrate", "non-rate", "no-rate"}:
        # UX requirement: Fixed vs Floating only.
        return "Floating"
    return None


def _rate_display(tipo_tasa: str | None, tasa_fija: float | None) -> float | None:
    raw = (tipo_tasa or "").strip().lower()

    if raw in {"fijo", "fixed"}:
        return tasa_fija

    if raw in {"nonrate", "non-rate", "no-rate"}:
        # Explicit fallback accepted by requirements.
        return tasa_fija

    if raw in {"variable", "floating", "float"}:
        # Requirement: do not invent tenor proxy here.
        return tasa_fija

    return tasa_fija


def _maturity_years(fecha_vencimiento: str | None, fallback_years: float | None) -> float | None:
    if fecha_vencimiento:
        try:
            venc = datetime.fromisoformat(fecha_vencimiento).date()
            now = datetime.now(timezone.utc).date()
            years = (venc - now).days / 365.25
            if years >= 0:
                return years
        except Exception:
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


def _weighted_avg_rate(rows: list[dict[str, Any]]) -> float | None:
    weighted_sum = 0.0
    weight = 0.0

    for row in rows:
        amount = _to_float(row.get("amount")) or 0.0
        rate = _to_float(row.get("rate_display"))
        if rate is None or amount == 0:
            continue
        w = abs(amount)
        weighted_sum += rate * w
        weight += w

    if weight == 0:
        return None
    return weighted_sum / weight


def _weighted_avg_maturity(rows: list[dict[str, Any]]) -> float | None:
    weighted_sum = 0.0
    weight = 0.0

    for row in rows:
        amount = _to_float(row.get("amount")) or 0.0
        maturity = _to_float(row.get("maturity_years"))
        if maturity is None or amount == 0:
            continue
        w = abs(amount)
        weighted_sum += maturity * w
        weight += w

    if weight == 0:
        return None
    return weighted_sum / weight


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


def _canonicalize_position_row(sheet_name: str, record: dict[str, Any], idx: int) -> dict[str, Any]:
    lookup = {_norm_key(k): k for k in record.keys()}

    def get(col: str) -> Any:
        key = lookup.get(col)
        if key is None:
            return None
        return record.get(key)

    contract_id = _to_text(get("num_sec_ac")) or f"{_slugify(sheet_name)}-{idx + 1}"
    side = _normalize_side(_to_text(get("lado_balance")), sheet_name)

    categoria_ui = _normalize_categoria_ui(_to_text(get("categoria_ui")), side)
    subcategoria_ui = _to_text(get("subcategoria_ui")) or sheet_name
    subcategory_id = _to_subcategory_id(subcategoria_ui, sheet_name)

    amount = _to_float(get("saldo_ini"))
    if amount is None:
        amount = 0.0

    book_value = _to_float(get("book_value"))
    tasa_fija = _to_float(get("tasa_fija"))

    tipo_tasa = _to_text(get("tipo_tasa"))
    rate_type = _normalize_rate_type(tipo_tasa)
    rate_display = _rate_display(tipo_tasa, tasa_fija)

    fecha_inicio = _to_iso_date(get("fecha_inicio"))
    fecha_vencimiento = _to_iso_date(get("fecha_vencimiento"))
    fecha_prox_reprecio = _to_iso_date(get("fecha_prox_reprecio"))

    core_avg_maturity = _to_float(get("core_avg_maturity_y"))
    maturity_years = _maturity_years(fecha_vencimiento, core_avg_maturity)
    if subcategory_id == "deposits":
        # Temporary business rule: treat non-maturity deposits as 0Y until behavioural treatment is implemented.
        maturity_years = 0.0

    maturity_bucket = _to_text(get("bucket_vencimiento")) or _bucket_from_years(maturity_years)
    if subcategory_id == "deposits":
        maturity_bucket = "<1Y"
    repricing_bucket = _to_text(get("bucket_reprecio"))

    return {
        "contract_id": contract_id,
        "sheet": sheet_name,
        "side": side,
        "categoria_ui": categoria_ui,
        "subcategoria_ui": subcategoria_ui,
        "subcategory_id": subcategory_id,
        "group": _to_text(get("grupo")),
        "currency": _to_text(get("moneda")),
        "counterparty": _to_text(get("contraparte")),
        "amount": amount,
        "book_value": book_value,
        "rate_type": rate_type,
        "rate_display": rate_display,
        "tipo_tasa_raw": tipo_tasa,
        "tasa_fija": tasa_fija,
        "spread": _to_float(get("spread")),
        "indice_ref": _to_text(get("indice_ref")),
        "tenor_indice": _to_text(get("tenor_indice")),
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_prox_reprecio": fecha_prox_reprecio,
        "maturity_years": maturity_years,
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": repricing_bucket,
        "include_in_balance_tree": side in {"asset", "liability"},
    }


def _validate_base_sheet_columns(sheet_name: str, df: pd.DataFrame) -> None:
    normalized = {_norm_key(c) for c in df.columns}
    missing = sorted(BASE_REQUIRED_COLS - normalized)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Sheet '{sheet_name}' is missing required columns: {', '.join(missing)}. "
                "Expected via1 schema for A_/L_/E_ sheets."
            ),
        )


def _is_position_sheet(sheet_name: str) -> bool:
    if sheet_name in META_SHEETS:
        return False
    return sheet_name.startswith(POSITION_PREFIXES)


def _subcategory_sort_key(side: str, subcategory_id: str, label: str, amount: float) -> tuple[int, float, str]:
    if side == "asset":
        if subcategory_id in ASSET_SUBCATEGORY_ORDER:
            return (0, ASSET_SUBCATEGORY_ORDER.index(subcategory_id), label)
    elif side == "liability":
        if subcategory_id in LIABILITY_SUBCATEGORY_ORDER:
            return (0, LIABILITY_SUBCATEGORY_ORDER.index(subcategory_id), label)

    # Keep unknown categories stable by amount desc then label.
    return (1, -amount, label)


def _build_category_tree(rows: list[dict[str, Any]], side: str, label: str, cat_id: str) -> BalanceTreeCategory | None:
    scoped = [r for r in rows if r.get("side") == side and r.get("include_in_balance_tree")]
    if not scoped:
        return None

    grouped: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}

    for row in scoped:
        sid = str(row.get("subcategory_id") or "unknown")
        grouped.setdefault(sid, []).append(row)
        labels[sid] = str(row.get("subcategoria_ui") or sid)

    subcategories: list[BalanceTreeNode] = []
    for sid, sub_rows in grouped.items():
        amount = float(sum((_to_float(r.get("amount")) or 0.0) for r in sub_rows))
        positions = len(sub_rows)
        avg_rate = _weighted_avg_rate(sub_rows)
        avg_maturity = _weighted_avg_maturity(sub_rows)
        subcategories.append(
            BalanceTreeNode(
                id=sid,
                label=labels.get(sid, sid),
                amount=amount,
                positions=positions,
                avg_rate=avg_rate,
                avg_maturity=avg_maturity,
            )
        )

    subcategories = sorted(
        subcategories,
        key=lambda node: _subcategory_sort_key(side, node.id, node.label, node.amount),
    )

    amount = float(sum(node.amount for node in subcategories))
    positions = int(sum(node.positions for node in subcategories))
    avg_rate = _weighted_avg_rate(scoped)
    avg_maturity = _weighted_avg_maturity(scoped)

    return BalanceTreeCategory(
        id=cat_id,
        label=label,
        amount=amount,
        positions=positions,
        avg_rate=avg_rate,
        avg_maturity=avg_maturity,
        subcategories=subcategories,
    )


def _build_optional_side_tree(rows: list[dict[str, Any]], side: str, label: str, cat_id: str) -> BalanceTreeCategory | None:
    scoped = [r for r in rows if r.get("side") == side]
    if not scoped:
        return None

    grouped: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}
    for row in scoped:
        sid = str(row.get("subcategory_id") or "unknown")
        grouped.setdefault(sid, []).append(row)
        labels[sid] = str(row.get("subcategoria_ui") or sid)

    subcategories: list[BalanceTreeNode] = []
    for sid, sub_rows in grouped.items():
        subcategories.append(
            BalanceTreeNode(
                id=sid,
                label=labels.get(sid, sid),
                amount=float(sum((_to_float(r.get("amount")) or 0.0) for r in sub_rows)),
                positions=len(sub_rows),
                avg_rate=_weighted_avg_rate(sub_rows),
                avg_maturity=_weighted_avg_maturity(sub_rows),
            )
        )

    subcategories = sorted(subcategories, key=lambda x: x.label.lower())

    return BalanceTreeCategory(
        id=cat_id,
        label=label,
        amount=float(sum(node.amount for node in subcategories)),
        positions=int(sum(node.positions for node in subcategories)),
        avg_rate=_weighted_avg_rate(scoped),
        avg_maturity=_weighted_avg_maturity(scoped),
        subcategories=subcategories,
    )


def _build_summary_tree(rows: list[dict[str, Any]]) -> BalanceSummaryTree:
    return BalanceSummaryTree(
        assets=_build_category_tree(rows, side="asset", label="Assets", cat_id="assets"),
        liabilities=_build_category_tree(rows, side="liability", label="Liabilities", cat_id="liabilities"),
        equity=_build_optional_side_tree(rows, side="equity", label="Equity", cat_id="equity"),
        derivatives=_build_optional_side_tree(rows, side="derivative", label="Derivatives", cat_id="derivatives"),
    )


def _parse_workbook(xlsx_path: Path) -> tuple[list[BalanceSheetSummary], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    try:
        xls = pd.ExcelFile(xlsx_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read Excel file: {exc}")

    sheet_summaries: list[BalanceSheetSummary] = []
    sample_rows: dict[str, list[dict[str, Any]]] = {}
    canonical_rows: list[dict[str, Any]] = []

    for sheet_name in xls.sheet_names:
        if not _is_position_sheet(sheet_name):
            continue

        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
        sheet_summaries.append(_safe_sheet_summary(sheet_name, df))

        # JSON-safe sample rows for debug and add-flow templates.
        sample_rows[sheet_name] = [
            {str(k): _serialize_value_for_json(v) for k, v in rec.items()}
            for rec in df.head(3).to_dict(orient="records")
        ]

        if sheet_name.startswith(("A_", "L_", "E_")):
            _validate_base_sheet_columns(sheet_name, df)

        records = df.to_dict(orient="records")
        for idx, rec in enumerate(records):
            canonical_rows.append(_canonicalize_position_row(sheet_name, rec, idx))

    return sheet_summaries, sample_rows, canonical_rows


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


def _persist_balance_payload(session_id: str, response: BalanceUploadResponse, canonical_rows: list[dict[str, Any]]) -> None:
    sdir = _session_dir(session_id)
    _summary_path(session_id).write_text(response.model_dump_json(indent=2), encoding="utf-8")

    positions_json = json.dumps(canonical_rows, indent=2, ensure_ascii=False)
    _positions_path(session_id).write_text(positions_json, encoding="utf-8")

    # Keep compatibility with older consumers.
    contracts_payload = [
        {
            "contract_id": row.get("contract_id"),
            "sheet": row.get("sheet"),
            "subcategory": row.get("subcategory_id"),
            "category": row.get("side"),
            "categoria_ui": row.get("categoria_ui"),
            "subcategoria_ui": row.get("subcategoria_ui"),
            "group": row.get("group"),
            "currency": row.get("currency"),
            "counterparty": row.get("counterparty"),
            "rate_type": row.get("rate_type"),
            "maturity_bucket": row.get("maturity_bucket"),
            "maturity_years": row.get("maturity_years"),
            "amount": row.get("amount"),
            "rate": row.get("rate_display"),
        }
        for row in canonical_rows
        if row.get("include_in_balance_tree")
    ]
    (sdir / "balance_contracts.json").write_text(
        json.dumps(contracts_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_and_store_balance(session_id: str, filename: str, xlsx_path: Path) -> BalanceUploadResponse:
    sheet_summaries, sample_rows, canonical_rows = _parse_workbook(xlsx_path)

    summary_tree = _build_summary_tree(canonical_rows)
    response = BalanceUploadResponse(
        session_id=session_id,
        filename=filename,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        sheets=sheet_summaries,
        sample_rows=sample_rows,
        summary_tree=summary_tree,
    )

    _persist_balance_payload(session_id, response, canonical_rows)
    return response


def _apply_positions_compat_defaults(rows: list[dict[str, Any]]) -> bool:
    changed = False
    for row in rows:
        subcategory_id = str(row.get("subcategory_id") or "").lower()
        if subcategory_id == "deposits":
            maturity_years = _to_float(row.get("maturity_years"))
            if maturity_years is None or abs(maturity_years) > 1e-9:
                row["maturity_years"] = 0.0
                changed = True
            if row.get("maturity_bucket") != "<1Y":
                row["maturity_bucket"] = "<1Y"
                changed = True
    return changed


def _load_or_rebuild_summary(session_id: str) -> BalanceUploadResponse:
    summary_file = _summary_path(session_id)
    if summary_file.exists():
        payload = json.loads(summary_file.read_text(encoding="utf-8"))
        response = BalanceUploadResponse(**payload)

        positions_file = _positions_path(session_id)
        if positions_file.exists():
            rows = json.loads(positions_file.read_text(encoding="utf-8"))
            rows_changed = _apply_positions_compat_defaults(rows)
            if rows_changed:
                positions_file.write_text(
                    json.dumps(rows, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

            response.summary_tree = _build_summary_tree(rows)
            summary_file.write_text(response.model_dump_json(indent=2), encoding="utf-8")

        return response

    xlsx_path = _latest_balance_file(session_id)
    filename = xlsx_path.name.removeprefix("balance__")
    return _parse_and_store_balance(session_id, filename=filename, xlsx_path=xlsx_path)


def _load_or_rebuild_positions(session_id: str) -> list[dict[str, Any]]:
    positions_file = _positions_path(session_id)
    if positions_file.exists():
        rows = json.loads(positions_file.read_text(encoding="utf-8"))
        if _apply_positions_compat_defaults(rows):
            positions_file.write_text(
                json.dumps(rows, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return rows

    _load_or_rebuild_summary(session_id)
    if positions_file.exists():
        rows = json.loads(positions_file.read_text(encoding="utf-8"))
        if _apply_positions_compat_defaults(rows):
            positions_file.write_text(
                json.dumps(rows, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return rows

    raise HTTPException(status_code=404, detail="No balance uploaded for this session yet")


# -------------------------
# Filtering and aggregations
# -------------------------
def _split_csv_values(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    values = []
    for token in raw.split(","):
        cleaned = token.strip()
        if cleaned:
            values.append(cleaned.lower())
    return set(values)


def _normalize_category_filter(raw: str | None) -> set[str]:
    values = _split_csv_values(raw)
    out: set[str] = set()
    for value in values:
        if value in {"assets", "asset"}:
            out.add("asset")
        elif value in {"liabilities", "liability"}:
            out.add("liability")
        elif value in {"equity"}:
            out.add("equity")
        elif value in {"derivatives", "derivative"}:
            out.add("derivative")
    return out


def _matches_multi(value: str | None, allowed: set[str]) -> bool:
    if not allowed:
        return True
    if value is None:
        return False
    return value.lower() in allowed


def _matches_subcategory(row: dict[str, Any], subcategoria_ui: str | None, subcategory_id: str | None) -> bool:
    if not subcategoria_ui and not subcategory_id:
        return True

    row_id = str(row.get("subcategory_id") or "").lower()
    row_label = str(row.get("subcategoria_ui") or "").lower()

    if subcategory_id and row_id != subcategory_id.strip().lower():
        return False

    if subcategoria_ui:
        wanted = subcategoria_ui.strip().lower()
        if row_label != wanted and row_id != _to_subcategory_id(subcategoria_ui, "").lower():
            return False

    return True


def _apply_filters(
    rows: list[dict[str, Any]],
    *,
    categoria_ui: str | None = None,
    subcategoria_ui: str | None = None,
    subcategory_id: str | None = None,
    group: str | None = None,
    currency: str | None = None,
    rate_type: str | None = None,
    counterparty: str | None = None,
    maturity: str | None = None,
    query_text: str | None = None,
) -> list[dict[str, Any]]:
    category_filter = _normalize_category_filter(categoria_ui)
    currency_filter = _split_csv_values(currency)
    rate_filter = _split_csv_values(rate_type)
    counterparty_filter = _split_csv_values(counterparty)
    maturity_filter = _split_csv_values(maturity)
    group_filter = _split_csv_values(group)

    query_norm = (query_text or "").strip().lower()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("include_in_balance_tree"):
            continue

        side = str(row.get("side") or "").lower()
        if category_filter and side not in category_filter:
            continue

        if not _matches_subcategory(row, subcategoria_ui, subcategory_id):
            continue

        row_group = _to_text(row.get("group"))
        if not _matches_multi(row_group, group_filter):
            continue

        row_currency = _to_text(row.get("currency"))
        if not _matches_multi(row_currency, currency_filter):
            continue

        row_rate_type = _to_text(row.get("rate_type"))
        if not _matches_multi(row_rate_type, rate_filter):
            continue

        row_counterparty = _to_text(row.get("counterparty"))
        if not _matches_multi(row_counterparty, counterparty_filter):
            continue

        row_maturity = _to_text(row.get("maturity_bucket"))
        if not _matches_multi(row_maturity, maturity_filter):
            continue

        if query_norm:
            contract_id = str(row.get("contract_id") or "").lower()
            sheet_name = str(row.get("sheet") or "").lower()
            group_name = str(row.get("group") or "").lower()
            if query_norm not in contract_id and query_norm not in sheet_name and query_norm not in group_name:
                continue

        filtered.append(row)

    return filtered


def _build_facets(rows: list[dict[str, Any]]) -> BalanceDetailsFacets:
    def count_values(field: str) -> list[FacetOption]:
        counts: dict[str, int] = {}
        for row in rows:
            value = _to_text(row.get(field))
            if value is None:
                continue
            counts[value] = counts.get(value, 0) + 1
        return [FacetOption(value=k, count=v) for k, v in sorted(counts.items(), key=lambda item: item[0].lower())]

    return BalanceDetailsFacets(
        currencies=count_values("currency"),
        rate_types=count_values("rate_type"),
        counterparties=count_values("counterparty"),
        maturities=count_values("maturity_bucket"),
    )


def _aggregate_groups(rows: list[dict[str, Any]]) -> list[BalanceDetailsGroup]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group = _to_text(row.get("group")) or "Ungrouped"
        grouped.setdefault(group, []).append(row)

    items: list[BalanceDetailsGroup] = []
    for group, group_rows in grouped.items():
        amount = float(sum((_to_float(r.get("amount")) or 0.0) for r in group_rows))
        items.append(
            BalanceDetailsGroup(
                group=group,
                amount=amount,
                positions=len(group_rows),
                avg_rate=_weighted_avg_rate(group_rows),
                avg_maturity=_weighted_avg_maturity(group_rows),
            )
        )

    return sorted(items, key=lambda x: x.amount, reverse=True)


def _aggregate_totals(rows: list[dict[str, Any]]) -> BalanceDetailsTotals:
    return BalanceDetailsTotals(
        amount=float(sum((_to_float(r.get("amount")) or 0.0) for r in rows)),
        positions=len(rows),
        avg_rate=_weighted_avg_rate(rows),
        avg_maturity=_weighted_avg_maturity(rows),
    )


# -------------------------
# API routes
# -------------------------
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sessions", response_model=SessionMeta)
def create_session() -> SessionMeta:
    session_id = str(uuid.uuid4())
    meta = SessionMeta(
        session_id=session_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="active",
        schema_version="v1",
    )
    _SESSIONS[session_id] = meta
    _persist_session_meta(meta)
    return meta


@app.get("/api/sessions/{session_id}", response_model=SessionMeta)
def get_session(session_id: str) -> SessionMeta:
    _assert_session_exists(session_id)
    return _get_session_meta(session_id)


@app.post("/api/sessions/{session_id}/curves", response_model=CurvesSummaryResponse)
async def upload_curves(session_id: str, file: UploadFile = File(...)) -> CurvesSummaryResponse:
    _assert_session_exists(session_id)

    raw_filename = file.filename or "curves.xlsx"
    if not raw_filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx/.xls files are supported")

    safe_filename = Path(raw_filename).name
    storage_name = f"curves__{safe_filename}"

    sdir = _session_dir(session_id)
    xlsx_path = sdir / storage_name
    content = await file.read()
    xlsx_path.write_bytes(content)

    return _parse_and_store_curves(session_id, filename=safe_filename, xlsx_path=xlsx_path)


@app.get("/api/sessions/{session_id}/curves/summary", response_model=CurvesSummaryResponse)
def get_curves_summary(session_id: str) -> CurvesSummaryResponse:
    _assert_session_exists(session_id)
    return _load_or_rebuild_curves_summary(session_id)


@app.get("/api/sessions/{session_id}/curves/{curve_id}", response_model=CurvePointsResponse)
def get_curve_points(session_id: str, curve_id: str) -> CurvePointsResponse:
    _assert_session_exists(session_id)
    points_by_curve = _load_or_rebuild_curve_points(session_id)
    points = points_by_curve.get(curve_id)
    if points is None:
        raise HTTPException(status_code=404, detail=f"Curve '{curve_id}' not found for this session")

    return CurvePointsResponse(session_id=session_id, curve_id=curve_id, points=points)


@app.post("/api/sessions/{session_id}/balance", response_model=BalanceUploadResponse)
async def upload_balance(session_id: str, file: UploadFile = File(...)) -> BalanceUploadResponse:
    _assert_session_exists(session_id)

    raw_filename = file.filename or "balance.xlsx"
    if not raw_filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx/.xls files are supported")

    safe_filename = Path(raw_filename).name
    storage_name = f"balance__{safe_filename}"

    sdir = _session_dir(session_id)
    xlsx_path = sdir / storage_name
    content = await file.read()
    xlsx_path.write_bytes(content)

    return _parse_and_store_balance(session_id, filename=safe_filename, xlsx_path=xlsx_path)


@app.get("/api/sessions/{session_id}/balance/summary", response_model=BalanceUploadResponse)
def get_balance_summary(session_id: str) -> BalanceUploadResponse:
    _assert_session_exists(session_id)
    return _load_or_rebuild_summary(session_id)


@app.get("/api/sessions/{session_id}/balance/details", response_model=BalanceDetailsResponse)
def get_balance_details(
    session_id: str,
    categoria_ui: str | None = None,
    subcategoria_ui: str | None = None,
    subcategory_id: str | None = None,
    currency: str | None = None,
    rate_type: str | None = None,
    counterparty: str | None = None,
    maturity: str | None = None,
) -> BalanceDetailsResponse:
    _assert_session_exists(session_id)

    rows = _load_or_rebuild_positions(session_id)

    # Context rows define what can be shown in facets.
    context_rows = _apply_filters(
        rows,
        categoria_ui=categoria_ui,
        subcategoria_ui=subcategoria_ui,
        subcategory_id=subcategory_id,
    )

    filtered_rows = _apply_filters(
        context_rows,
        currency=currency,
        rate_type=rate_type,
        counterparty=counterparty,
        maturity=maturity,
    )

    groups = _aggregate_groups(filtered_rows)
    totals = _aggregate_totals(filtered_rows)
    facets = _build_facets(context_rows)

    pretty_subcategory = subcategoria_ui
    if pretty_subcategory is None and subcategory_id:
        first = next((r for r in context_rows if str(r.get("subcategory_id")) == subcategory_id), None)
        pretty_subcategory = _to_text(first.get("subcategoria_ui")) if first else subcategory_id

    return BalanceDetailsResponse(
        session_id=session_id,
        categoria_ui=categoria_ui,
        subcategoria_ui=pretty_subcategory,
        groups=groups,
        totals=totals,
        facets=facets,
    )


@app.get("/api/sessions/{session_id}/balance/contracts", response_model=BalanceContractsResponse)
def get_balance_contracts(
    session_id: str,
    query: str | None = None,
    q: str | None = None,
    categoria_ui: str | None = None,
    subcategoria_ui: str | None = None,
    subcategory_id: str | None = None,
    group: str | None = None,
    currency: str | None = None,
    rate_type: str | None = None,
    counterparty: str | None = None,
    maturity: str | None = None,
    page: int = 1,
    page_size: int = 100,
    offset: int | None = None,
    limit: int | None = None,
) -> BalanceContractsResponse:
    _assert_session_exists(session_id)

    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")

    # Backward compatibility: old client used offset+limit.
    if offset is not None or limit is not None:
        effective_offset = max(offset or 0, 0)
        effective_limit = limit or 200
        if effective_limit <= 0 or effective_limit > 2000:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
        effective_page = (effective_offset // effective_limit) + 1
        effective_page_size = effective_limit
    else:
        effective_page = page
        effective_page_size = page_size

    if effective_page_size <= 0 or effective_page_size > 2000:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 2000")

    rows = _load_or_rebuild_positions(session_id)

    query_text = query if query is not None else q
    filtered = _apply_filters(
        rows,
        categoria_ui=categoria_ui,
        subcategoria_ui=subcategoria_ui,
        subcategory_id=subcategory_id,
        group=group,
        currency=currency,
        rate_type=rate_type,
        counterparty=counterparty,
        maturity=maturity,
        query_text=query_text,
    )

    total = len(filtered)
    start = (effective_page - 1) * effective_page_size
    end = start + effective_page_size

    sliced_rows = filtered[start:end]
    contracts = [
        BalanceContract(
            contract_id=str(row.get("contract_id") or ""),
            sheet=_to_text(row.get("sheet")),
            category=str(row.get("side") or ""),
            categoria_ui=_to_text(row.get("categoria_ui")),
            subcategory=str(row.get("subcategory_id") or "unknown"),
            subcategoria_ui=_to_text(row.get("subcategoria_ui")),
            group=_to_text(row.get("group")),
            currency=_to_text(row.get("currency")),
            counterparty=_to_text(row.get("counterparty")),
            rate_type=_to_text(row.get("rate_type")),
            maturity_bucket=_to_text(row.get("maturity_bucket")),
            maturity_years=_to_float(row.get("maturity_years")),
            amount=_to_float(row.get("amount")),
            rate=_to_float(row.get("rate_display")),
        )
        for row in sliced_rows
    ]

    return BalanceContractsResponse(
        session_id=session_id,
        total=total,
        page=effective_page,
        page_size=effective_page_size,
        contracts=contracts,
    )
