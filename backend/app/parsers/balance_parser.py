"""Balance parsing: canonicalization, tree building, Excel/ZIP parsing, persistence."""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import orjson
import pandas as pd
from fastapi import HTTPException

import app.state as state
from app.config import (
    ASSET_SUBCATEGORY_ORDER,
    LIABILITY_SUBCATEGORY_ORDER,
    BASE_REQUIRED_COLS,
    META_SHEETS,
    POSITION_PREFIXES,
    _BC_SIDE_UI,
    _EXCLUDED_CONTRACT_TYPES,
    _bc_classify,
    _bc_get_rules,
)
from engine.balance_config.classifier import _APARTADO_SIDE
from engine.balance_config.schema import (
    ASSET_DEFAULT,
    LIABILITY_DEFAULT,
    SUBCATEGORY_LABELS,
)
from app.schemas import (
    BalanceSheetSummary,
    BalanceSummaryTree,
    BalanceTreeCategory,
    BalanceTreeNode,
    BalanceUploadResponse,
)
from app.session import (
    _latest_balance_file,
    _motor_positions_path,
    _positions_path,
    _session_dir,
    _summary_path,
)
from app.parsers.transforms import (
    _bucket_from_years,
    _maturity_years,
    _norm_key,
    _normalize_categoria_ui,
    _normalize_rate_type,
    _normalize_side,
    _safe_sheet_summary,
    _serialize_value_for_json,
    _slugify,
    _to_float,
    _to_iso_date,
    _to_subcategory_id,
    _to_text,
    _weighted_avg_maturity,
    _weighted_avg_rate,
)

_log = logging.getLogger(__name__)


# ── Canonicalization ────────────────────────────────────────────────────────

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
    rate_display_val = tasa_fija

    fecha_inicio = _to_iso_date(get("fecha_inicio"))
    fecha_vencimiento = _to_iso_date(get("fecha_vencimiento"))
    fecha_prox_reprecio = _to_iso_date(get("fecha_prox_reprecio"))

    core_avg_maturity = _to_float(get("core_avg_maturity_y"))
    maturity_years_val = _maturity_years(fecha_vencimiento, core_avg_maturity)
    if subcategory_id == "deposits":
        maturity_years_val = 0.0

    maturity_bucket = _to_text(get("bucket_vencimiento")) or _bucket_from_years(maturity_years_val)
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
        "rate_display": rate_display_val,
        "tipo_tasa_raw": tipo_tasa,
        "tasa_fija": tasa_fija,
        "spread": _to_float(get("spread")),
        "indice_ref": _to_text(get("indice_ref")),
        "tenor_indice": _to_text(get("tenor_indice")),
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_prox_reprecio": fecha_prox_reprecio,
        "maturity_years": maturity_years_val,
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": repricing_bucket,
        "include_in_balance_tree": side in {"asset", "liability"},
    }


def _canonicalize_motor_row(
    record: dict[str, Any],
    idx: int,
    client_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract_id = str(record.get("contract_id") or f"motor-{idx + 1}")
    source_contract_type = str(record.get("source_contract_type") or "unknown")
    raw_side = str(record.get("side") or "A").upper()

    rules = client_rules or {}
    cls = _bc_classify(
        apartado=_to_text(record.get("balance_section")),
        producto=_to_text(record.get("balance_product")),
        motor_side=raw_side,
        **rules,
    )
    side = cls.side
    categoria_ui = _BC_SIDE_UI.get(side, "Assets")
    subcategoria_ui = cls.subcategory_label
    subcategory_id = cls.subcategory_id

    amount = _to_float(record.get("notional")) or 0.0

    rate_type_raw = str(record.get("rate_type") or "")
    rate_type = (
        "Fixed" if rate_type_raw == "fixed"
        else "Floating" if rate_type_raw == "float"
        else None
    )
    fixed_rate = _to_float(record.get("fixed_rate"))
    spread_val = _to_float(record.get("spread"))
    rate_display_val = fixed_rate

    fecha_inicio = _to_iso_date(record.get("start_date"))
    fecha_vencimiento = _to_iso_date(record.get("maturity_date"))
    fecha_prox_reprecio = _to_iso_date(record.get("next_reprice_date"))

    mat_years = _maturity_years(fecha_vencimiento, None)
    is_non_maturity = "non_maturity" in source_contract_type
    if is_non_maturity:
        mat_years = 0.0

    maturity_bucket = _bucket_from_years(mat_years)
    if is_non_maturity:
        maturity_bucket = "<1Y"

    return {
        "contract_id": contract_id,
        "sheet": source_contract_type,
        "side": side,
        "categoria_ui": categoria_ui,
        "subcategoria_ui": subcategoria_ui,
        "subcategory_id": subcategory_id,
        "group": subcategoria_ui,
        "currency": "EUR",
        "counterparty": None,
        "amount": amount,
        "book_value": None,
        "rate_type": rate_type,
        "rate_display": rate_display_val,
        "tipo_tasa_raw": rate_type_raw,
        "tasa_fija": fixed_rate,
        "spread": spread_val,
        "indice_ref": _to_text(record.get("index_name")),
        "tenor_indice": None,
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_prox_reprecio": fecha_prox_reprecio,
        "maturity_years": mat_years,
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": None,
        "include_in_balance_tree": side in {"asset", "liability"},
        "source_contract_type": source_contract_type,
        "daycount_base": _to_text(record.get("daycount_base")),
        "notional": amount,
        "repricing_freq": _to_text(record.get("repricing_freq")),
        "payment_freq": _to_text(record.get("payment_freq")),
        "floor_rate": _to_float(record.get("floor_rate")),
        "cap_rate": _to_float(record.get("cap_rate")),
        "balance_product": _to_text(record.get("balance_product")),
        "balance_section": _to_text(record.get("balance_section")),
        "balance_epigrafe": _to_text(record.get("balance_epigrafe")),
    }


# ── Vectorised motor canonicalization ─────────────────────────────────────────

def _classify_motor_df(
    motor_df: pd.DataFrame,
    client_rules: dict[str, Any],
) -> pd.DataFrame:
    """Vectorised balance classification: iterates over *rules* not *rows*."""
    n = len(motor_df)

    # Resolve side from apartado, fallback to motor side
    apartado = motor_df["balance_section"].fillna("").str.strip().str.upper() if "balance_section" in motor_df.columns else pd.Series("", index=motor_df.index)
    motor_side_raw = motor_df["side"].fillna("A").astype(str).str.upper()

    side_from_apart = apartado.map(_APARTADO_SIDE)
    side_from_motor = motor_side_raw.map({"A": "asset", "L": "liability"}).fillna("asset")
    side = side_from_apart.where(side_from_apart.notna(), side_from_motor)

    # Prepare producto for keyword matching
    producto = motor_df["balance_product"].fillna("").astype(str).str.upper() if "balance_product" in motor_df.columns else pd.Series("", index=motor_df.index)

    # Default subcategory_id per side
    subcategory_id = pd.Series(ASSET_DEFAULT, index=motor_df.index, dtype="object")
    subcategory_id = subcategory_id.where(side == "asset", LIABILITY_DEFAULT)
    subcategory_id = subcategory_id.where(side != "derivative", "derivatives")

    # Match rules: iterate over rules (~70), not rows (~1.5M)
    matched = pd.Series(False, index=motor_df.index)

    asset_rules: Sequence[tuple[str, str]] = client_rules.get("asset_rules", ())
    liability_rules: Sequence[tuple[str, str]] = client_rules.get("liability_rules", ())
    derivative_rules: Sequence[tuple[str, str]] = client_rules.get("derivative_rules", ())

    for keyword, sub_id in asset_rules:
        rule_match = (side == "asset") & ~matched & producto.str.contains(keyword.upper(), na=False, regex=False)
        subcategory_id = subcategory_id.where(~rule_match, sub_id)
        matched = matched | rule_match

    for keyword, sub_id in liability_rules:
        rule_match = (side == "liability") & ~matched & producto.str.contains(keyword.upper(), na=False, regex=False)
        subcategory_id = subcategory_id.where(~rule_match, sub_id)
        matched = matched | rule_match

    for keyword, sub_id in derivative_rules:
        rule_match = (side == "derivative") & ~matched & producto.str.contains(keyword.upper(), na=False, regex=False)
        subcategory_id = subcategory_id.where(~rule_match, sub_id)
        matched = matched | rule_match

    subcategory_label = subcategory_id.map(SUBCATEGORY_LABELS).fillna(
        subcategory_id.str.replace("-", " ").str.title()
    )

    return pd.DataFrame({
        "cls_side": side,
        "cls_subcategory_id": subcategory_id,
        "cls_subcategory_label": subcategory_label,
    }, index=motor_df.index)


def _canonicalize_motor_df(
    motor_df: pd.DataFrame,
    client_rules: dict[str, Any],
) -> list[dict[str, Any]]:
    """Vectorised version of _canonicalize_motor_row operating on the entire DataFrame."""
    n = len(motor_df)

    # Classification
    cls = _classify_motor_df(motor_df, client_rules)

    # Build canonical DataFrame with vectorised ops
    sct = motor_df["source_contract_type"].fillna("unknown").astype(str) if "source_contract_type" in motor_df.columns else pd.Series("unknown", index=motor_df.index)
    is_non_maturity = sct.str.contains("non_maturity", na=False, regex=False)

    # Contract ID
    idx_series = pd.Series(range(1, n + 1), index=motor_df.index, dtype="int64")
    contract_id = motor_df["contract_id"].fillna("motor-" + idx_series.astype(str)).astype(str) if "contract_id" in motor_df.columns else ("motor-" + idx_series.astype(str))

    # Amounts
    notional = pd.to_numeric(motor_df["notional"], errors="coerce").fillna(0.0) if "notional" in motor_df.columns else pd.Series(0.0, index=motor_df.index)

    # Rate type
    rate_type_raw = motor_df["rate_type"].fillna("").astype(str) if "rate_type" in motor_df.columns else pd.Series("", index=motor_df.index)
    rate_type = rate_type_raw.map({"fixed": "Fixed", "float": "Floating"})

    # Dates → ISO strings
    now = datetime.now(timezone.utc).date()

    def _col_to_iso(col_name: str) -> pd.Series:
        if col_name not in motor_df.columns:
            return pd.Series(None, index=motor_df.index, dtype="object")
        col = motor_df[col_name]
        dt = pd.to_datetime(col, errors="coerce")
        return dt.dt.strftime("%Y-%m-%d").where(dt.notna(), other=None)

    fecha_inicio = _col_to_iso("start_date")
    fecha_vencimiento = _col_to_iso("maturity_date")
    fecha_prox_reprecio = _col_to_iso("next_reprice_date")

    # Maturity years (vectorised)
    if "maturity_date" in motor_df.columns:
        mat_dt = pd.to_datetime(motor_df["maturity_date"], errors="coerce")
        mat_years = (mat_dt - pd.Timestamp(now)).dt.days / 365.25
        mat_years = mat_years.where(mat_years >= 0, other=np.nan)
        mat_years = mat_years.where(mat_dt.notna(), other=np.nan)
    else:
        mat_years = pd.Series(np.nan, index=motor_df.index)
    mat_years = mat_years.where(~is_non_maturity, 0.0)

    # Maturity bucket (vectorised)
    maturity_bucket = pd.cut(
        mat_years,
        bins=[-np.inf, 1, 5, 10, 20, np.inf],
        labels=["<1Y", "1-5Y", "5-10Y", "10-20Y", ">20Y"],
        right=False,
    ).astype("object")
    maturity_bucket = maturity_bucket.where(mat_years.notna(), other=None)
    maturity_bucket = maturity_bucket.where(~is_non_maturity, "<1Y")

    # Float columns
    def _float_col(name: str) -> pd.Series:
        if name not in motor_df.columns:
            return pd.Series(None, index=motor_df.index, dtype="object")
        return pd.to_numeric(motor_df[name], errors="coerce").where(
            pd.to_numeric(motor_df[name], errors="coerce").notna(), other=None
        )

    fixed_rate = _float_col("fixed_rate")
    spread_val = _float_col("spread")
    floor_rate = _float_col("floor_rate")
    cap_rate = _float_col("cap_rate")

    # Text columns
    def _text_col(name: str) -> pd.Series:
        if name not in motor_df.columns:
            return pd.Series(None, index=motor_df.index, dtype="object")
        s = motor_df[name].astype(str).str.strip()
        return s.where((motor_df[name].notna()) & s.ne("") & s.ne("nan") & s.ne("None") & s.ne("<NA>"), other=None)

    categoria_ui = cls["cls_side"].map(_BC_SIDE_UI).fillna("Assets")

    canonical_df = pd.DataFrame({
        "contract_id": contract_id,
        "sheet": sct,
        "side": cls["cls_side"],
        "categoria_ui": categoria_ui,
        "subcategoria_ui": cls["cls_subcategory_label"],
        "subcategory_id": cls["cls_subcategory_id"],
        "group": cls["cls_subcategory_label"],
        "currency": "EUR",
        "counterparty": None,
        "amount": notional,
        "book_value": None,
        "rate_type": rate_type,
        "rate_display": fixed_rate,
        "tipo_tasa_raw": rate_type_raw,
        "tasa_fija": fixed_rate,
        "spread": spread_val,
        "indice_ref": _text_col("index_name"),
        "tenor_indice": None,
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_prox_reprecio": fecha_prox_reprecio,
        "maturity_years": mat_years.where(mat_years.notna(), other=None),
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": None,
        "include_in_balance_tree": cls["cls_side"].isin({"asset", "liability"}),
        "source_contract_type": sct,
        "daycount_base": _text_col("daycount_base"),
        "notional": notional,
        "repricing_freq": _text_col("repricing_freq"),
        "payment_freq": _text_col("payment_freq"),
        "floor_rate": floor_rate,
        "cap_rate": cap_rate,
        "balance_product": _text_col("balance_product"),
        "balance_section": _text_col("balance_section"),
        "balance_epigrafe": _text_col("balance_epigrafe"),
    }, index=motor_df.index)

    # Convert NaN/NaT to None for clean JSON serialization
    canonical_df = canonical_df.astype(object).where(canonical_df.notna(), other=None)

    return canonical_df.to_dict(orient="records")


def _serialize_motor_df_to_parquet(motor_df: pd.DataFrame, path: Path) -> None:
    """Write motor DataFrame to Parquet (10-50x smaller/faster than JSON)."""
    motor_df.to_parquet(path, engine="pyarrow", index=False)


# ── Schema validation ───────────────────────────────────────────────────────

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


# ── Subcategory sorting ─────────────────────────────────────────────────────

def _subcategory_sort_key(side: str, subcategory_id: str, label: str, amount: float) -> tuple[int, float, str]:
    if side == "asset":
        if subcategory_id in ASSET_SUBCATEGORY_ORDER:
            return (0, ASSET_SUBCATEGORY_ORDER.index(subcategory_id), label)
    elif side == "liability":
        if subcategory_id in LIABILITY_SUBCATEGORY_ORDER:
            return (0, LIABILITY_SUBCATEGORY_ORDER.index(subcategory_id), label)

    return (1, -amount, label)


# ── Tree building ───────────────────────────────────────────────────────────

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


# ── Excel parsing ───────────────────────────────────────────────────────────

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


# ── ZIP/CSV parsing ─────────────────────────────────────────────────────────

def _parse_zip_balance(
    session_id: str,
    zip_path: Path,
) -> tuple[list[BalanceSheetSummary], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    from engine.config import bank_mapping_unicaja
    from engine.io.positions_pipeline import load_positions_from_specs

    sdir = _session_dir(session_id)

    # 1. Extract ZIP
    extract_dir = sdir / "balance_csvs"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    csv_files = list(extract_dir.glob("*.csv"))
    if not csv_files:
        subdirs = [
            d for d in extract_dir.iterdir()
            if d.is_dir() and d.name != "__MACOSX"
        ]
        if len(subdirs) == 1:
            extract_dir = subdirs[0]

    # 2. Run motor pipeline (vectorised CSV parsing)
    filtered_specs = [
        {**spec, "required": False}
        for spec in bank_mapping_unicaja.SOURCE_SPECS
        if spec.get("source_contract_type") not in _EXCLUDED_CONTRACT_TYPES
    ]

    def _report_progress(step: int, total: int) -> None:
        state._upload_progress[session_id] = {
            "step": step, "total": total, "phase": "parsing",
        }

    state._upload_progress[session_id] = {"step": 0, "total": len(filtered_specs), "phase": "parsing"}

    try:
        motor_df = load_positions_from_specs(
            root_path=extract_dir,
            mapping_module=bank_mapping_unicaja,
            source_specs=filtered_specs,
            on_progress=_report_progress,
        )
    except Exception as exc:
        state._upload_progress.pop(session_id, None)
        raise HTTPException(
            status_code=400,
            detail=f"Error parsing CSV positions: {exc}",
        )

    n_records = len(motor_df)
    _log.info("Parsed %d motor positions from ZIP", n_records)

    # 3. Persist motor DataFrame as Parquet (10-50x faster than JSON)
    state._upload_progress[session_id] = {"step": 0, "total": 1, "phase": "persisting"}
    _serialize_motor_df_to_parquet(motor_df, _motor_positions_path(session_id))
    state._upload_progress[session_id] = {"step": 1, "total": 1, "phase": "persisting"}

    # 4. Build UI-canonical rows (vectorised — iterates ~70 rules, not 1.5M rows)
    state._upload_progress[session_id] = {"step": 0, "total": 1, "phase": "canonicalizing"}
    client_rules = _bc_get_rules("unicaja")
    canonical_rows = _canonicalize_motor_df(motor_df, client_rules)
    state._upload_progress[session_id] = {"step": 1, "total": 1, "phase": "canonicalizing"}

    # 5. Build sheet summaries (vectorised groupby)
    sct_col = motor_df["source_contract_type"].fillna("unknown").astype(str) if "source_contract_type" in motor_df.columns else pd.Series("unknown", index=motor_df.index)
    contract_types = sorted(sct_col.unique())

    sheet_summaries: list[BalanceSheetSummary] = []
    sample_rows: dict[str, list[dict[str, Any]]] = {}

    # Index canonical_rows by sheet for efficient lookup
    canonical_by_sheet: dict[str, list[dict[str, Any]]] = {}
    for row in canonical_rows:
        ct = str(row.get("sheet", "unknown"))
        canonical_by_sheet.setdefault(ct, []).append(row)

    for ct in contract_types:
        ct_rows = canonical_by_sheet.get(ct, [])
        sheet_summaries.append(
            BalanceSheetSummary(
                sheet=ct,
                rows=len(ct_rows),
                columns=list(ct_rows[0].keys()) if ct_rows else [],
                total_saldo_ini=sum(r.get("amount", 0) for r in ct_rows),
            )
        )
        sample_rows[ct] = ct_rows[:3]

    return sheet_summaries, sample_rows, canonical_rows


# ── Motor DataFrame reconstruction ──────────────────────────────────────────

def _reconstruct_motor_dataframe(session_id: str) -> pd.DataFrame:
    motor_path = _motor_positions_path(session_id)

    # Backward compatibility: try new Parquet path first, then legacy JSON
    legacy_json_path = motor_path.with_suffix(".json")

    if motor_path.exists():
        df = pd.read_parquet(motor_path)
    elif legacy_json_path.exists():
        records = json.loads(legacy_json_path.read_text(encoding="utf-8"))
        if not records:
            raise HTTPException(status_code=400, detail="Motor positions file is empty")
        df = pd.DataFrame(records)
    else:
        raise HTTPException(
            status_code=404,
            detail="No motor positions found. Upload a balance ZIP first.",
        )

    if df.empty:
        raise HTTPException(status_code=400, detail="Motor positions file is empty")

    date_cols = ["start_date", "maturity_date", "next_reprice_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
            df[col] = df[col].where(df[col].notna(), other=None)

    numeric_cols = ["notional", "fixed_rate", "spread", "floor_rate", "cap_rate"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    _NON_MATURITY_TYPES = {"fixed_non_maturity", "variable_non_maturity",
                           "static_position", "non-maturity"}
    sct_col = "source_contract_type"
    if "maturity_date" in df.columns:
        needs_maturity = ~df[sct_col].str.lower().str.strip().isin(_NON_MATURITY_TYPES) if sct_col in df.columns else pd.Series(True, index=df.index)
        missing_maturity = needs_maturity & df["maturity_date"].isna()
        n_bad = int(missing_maturity.sum())
        if n_bad > 0:
            sample_ids = df.loc[missing_maturity, "contract_id"].head(5).tolist() if "contract_id" in df.columns else []
            _log.warning(
                "Dropping %d positions with missing maturity_date (e.g. %s)",
                n_bad, sample_ids,
            )
            df = df.loc[~missing_maturity].reset_index(drop=True)

    return df


# ── Balance persistence & lazy loading ──────────────────────────────────────

def _persist_balance_payload(session_id: str, response: BalanceUploadResponse, canonical_rows: list[dict[str, Any]]) -> None:
    sdir = _session_dir(session_id)
    _summary_path(session_id).write_text(response.model_dump_json(indent=2), encoding="utf-8")

    _positions_path(session_id).write_bytes(
        orjson.dumps(canonical_rows, option=orjson.OPT_NON_STR_KEYS)
    )

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
    (sdir / "balance_contracts.json").write_bytes(
        orjson.dumps(contracts_payload, option=orjson.OPT_NON_STR_KEYS)
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
            maturity_years_val = _to_float(row.get("maturity_years"))
            if maturity_years_val is None or abs(maturity_years_val) > 1e-9:
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
