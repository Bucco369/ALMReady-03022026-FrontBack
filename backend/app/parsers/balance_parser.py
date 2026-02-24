"""Balance parsing: canonicalization, tree building, Excel/ZIP parsing, persistence."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    from almready.config import bank_mapping_unicaja
    from almready.io.positions_pipeline import load_positions_from_specs

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

    # 2. Run motor pipeline
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

    # 3. Persist motor DataFrame
    motor_records = motor_df.to_dict(orient="records")
    n_records = len(motor_records)
    state._upload_progress[session_id] = {"step": 0, "total": n_records, "phase": "persisting"}
    for i, rec in enumerate(motor_records):
        for key, val in list(rec.items()):
            rec[key] = _serialize_value_for_json(val)
        if i % 200 == 0:
            state._upload_progress[session_id]["step"] = i

    _motor_positions_path(session_id).write_text(
        json.dumps(motor_records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 4. Build UI-canonical rows
    state._upload_progress[session_id] = {"step": 0, "total": n_records, "phase": "canonicalizing"}

    client_rules = _bc_get_rules("unicaja")

    canonical_rows: list[dict[str, Any]] = []
    for idx, rec in enumerate(motor_records):
        canonical_rows.append(_canonicalize_motor_row(rec, idx, client_rules=client_rules))
        if idx % 200 == 0:
            state._upload_progress[session_id]["step"] = idx

    # 5. Build sheet summaries
    contract_types = sorted({
        str(rec.get("source_contract_type", "unknown")) for rec in motor_records
    })

    sheet_summaries: list[BalanceSheetSummary] = []
    sample_rows: dict[str, list[dict[str, Any]]] = {}

    for ct in contract_types:
        ct_rows = [r for r in canonical_rows if r.get("sheet") == ct]
        sheet_summaries.append(
            BalanceSheetSummary(
                sheet=ct,
                rows=len(ct_rows),
                columns=list(ct_rows[0].keys()) if ct_rows else [],
                total_saldo_ini=sum(r.get("amount", 0) for r in ct_rows),
            )
        )
        sample_rows[ct] = [
            {k: _serialize_value_for_json(v) for k, v in r.items()}
            for r in ct_rows[:3]
        ]

    return sheet_summaries, sample_rows, canonical_rows


# ── Motor DataFrame reconstruction ──────────────────────────────────────────

def _reconstruct_motor_dataframe(session_id: str) -> pd.DataFrame:
    motor_path = _motor_positions_path(session_id)
    if not motor_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No motor positions found. Upload a balance ZIP first.",
        )

    records = json.loads(motor_path.read_text(encoding="utf-8"))
    if not records:
        raise HTTPException(status_code=400, detail="Motor positions file is empty")

    df = pd.DataFrame(records)

    date_cols = ["start_date", "maturity_date", "next_reprice_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
            df[col] = df[col].where(df[col].notna(), other=None)

    numeric_cols = ["notional", "fixed_rate", "spread", "floor_rate", "cap_rate"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    import logging as _logging
    _NON_MATURITY_TYPES = {"fixed_non_maturity", "variable_non_maturity",
                           "static_position", "non-maturity"}
    sct_col = "source_contract_type"
    if "maturity_date" in df.columns:
        needs_maturity = ~df[sct_col].str.lower().str.strip().isin(_NON_MATURITY_TYPES) if sct_col in df.columns else pd.Series(True, index=df.index)
        missing_maturity = needs_maturity & df["maturity_date"].isna()
        n_bad = int(missing_maturity.sum())
        if n_bad > 0:
            sample_ids = df.loc[missing_maturity, "contract_id"].head(5).tolist() if "contract_id" in df.columns else []
            _logging.getLogger(__name__).warning(
                "Dropping %d positions with missing maturity_date (e.g. %s)",
                n_bad, sample_ids,
            )
            df = df.loc[~missing_maturity].reset_index(drop=True)

    return df


# ── Balance persistence & lazy loading ──────────────────────────────────────

def _persist_balance_payload(session_id: str, response: BalanceUploadResponse, canonical_rows: list[dict[str, Any]]) -> None:
    sdir = _session_dir(session_id)
    _summary_path(session_id).write_text(response.model_dump_json(indent=2), encoding="utf-8")

    positions_json = json.dumps(canonical_rows, indent=2, ensure_ascii=False)
    _positions_path(session_id).write_text(positions_json, encoding="utf-8")

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
