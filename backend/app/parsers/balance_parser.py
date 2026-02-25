"""Balance parsing orchestrator: Excel/ZIP upload, motor reconstruction, lazy loading."""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException

import app.state as state
from app.bank_adapters import BankAdapter
from app.config import BASE_REQUIRED_COLS, META_SHEETS, POSITION_PREFIXES, _bc_get_rules
from app.schemas import BalanceSheetSummary, BalanceUploadResponse
from app.session import (
    _latest_balance_file,
    _motor_positions_path,
    _positions_path,
    _session_dir,
    _summary_path,
)
from app.parsers._canonicalization import (
    _canonicalize_motor_df,
    _canonicalize_position_row,
    _serialize_motor_df_to_parquet,
)
from app.parsers._tree_builder import _build_summary_tree, _build_summary_tree_df
from app.parsers._persistence import (
    _persist_balance_payload,
    _read_positions_file,
)
from app.parsers.transforms import _norm_key, _safe_sheet_summary, _serialize_value_for_json

_log = logging.getLogger(__name__)


# ── Progress tracking helper ─────────────────────────────────────────────────

class _UploadProgress:
    """Thin wrapper to keep progress tracking out of business logic."""

    def __init__(self, session_id: str):
        self._sid = session_id

    def update(self, phase: str, step: int = 0, total: int = 1) -> None:
        state._upload_progress[self._sid] = {
            "step": step, "total": total, "phase": phase,
        }

    def clear(self) -> None:
        state._upload_progress.pop(self._sid, None)


# ── Schema validation ────────────────────────────────────────────────────────

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


# ── Excel parsing ────────────────────────────────────────────────────────────

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


# ── ZIP/CSV parsing ──────────────────────────────────────────────────────────

def _parse_zip_balance(
    session_id: str,
    zip_path: Path,
    filename: str,
    *,
    adapter: BankAdapter,
) -> BalanceUploadResponse:
    import os
    from engine.io.positions_pipeline import load_positions_from_specs

    sdir = _session_dir(session_id)
    progress = _UploadProgress(session_id)

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

    # 2. Run motor pipeline — PARALLEL CSV parsing
    filtered_specs = [
        {**spec, "required": False}
        for spec in adapter.mapping_module.SOURCE_SPECS
        if spec.get("source_contract_type") not in adapter.excluded_contract_types
    ]

    progress.update("parsing", 0, len(filtered_specs))

    def _report_progress(step: int, total: int) -> None:
        progress.update("parsing", step, total)

    n_workers = min(len(filtered_specs), os.cpu_count() or 4)

    try:
        motor_df = load_positions_from_specs(
            root_path=extract_dir,
            mapping_module=adapter.mapping_module,
            source_specs=filtered_specs,
            on_progress=_report_progress,
            parallel=n_workers,
        )
    except Exception as exc:
        progress.clear()
        raise HTTPException(
            status_code=400,
            detail=f"Error parsing CSV positions: {exc}",
        )

    n_records = len(motor_df)
    _log.info("Parsed %d motor positions from ZIP (%d workers)", n_records, n_workers)

    # 3. Persist motor DataFrame as Parquet
    progress.update("persisting")
    _serialize_motor_df_to_parquet(motor_df, _motor_positions_path(session_id))

    # 4. Build UI-canonical DataFrame (vectorised — iterates ~70 rules, not rows)
    #    Returns pd.DataFrame — NO dict round-trip.
    progress.update("canonicalizing")
    client_rules = _bc_get_rules(adapter.client_id)
    canonical_df = _canonicalize_motor_df(motor_df, client_rules)

    # Free motor_df memory — it's persisted to Parquet and no longer needed
    del motor_df

    # 5. Build sheet summaries (vectorised groupby on DataFrame)
    sheet_col = canonical_df["sheet"].fillna("unknown").astype(str)
    sheet_summaries: list[BalanceSheetSummary] = []
    sample_rows: dict[str, list[dict[str, Any]]] = {}

    amount_col = pd.to_numeric(canonical_df["amount"], errors="coerce").fillna(0.0)
    for ct, grp_idx in sheet_col.groupby(sheet_col).groups.items():
        n_rows = len(grp_idx)
        total_amount = float(amount_col.iloc[grp_idx].sum()) if n_rows > 0 else 0.0
        sheet_summaries.append(
            BalanceSheetSummary(
                sheet=str(ct),
                rows=n_rows,
                columns=list(canonical_df.columns),
                total_saldo_ini=total_amount,
            )
        )
        # Only materialize 3 sample rows per sheet (not 1.5M dicts)
        sample_slice = canonical_df.iloc[grp_idx[:3]]
        sample_rows[str(ct)] = sample_slice.to_dict(orient="records")

    sheet_summaries.sort(key=lambda s: s.sheet)

    # 6. Build summary tree (vectorised groupby — no Python row iteration)
    progress.update("building_tree")
    summary_tree = _build_summary_tree_df(canonical_df)

    # 7. Persist all data — DataFrame goes directly to Parquet (no reconstruction)
    progress.update("saving")
    response = BalanceUploadResponse(
        session_id=session_id,
        filename=filename,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        sheets=sheet_summaries,
        sample_rows=sample_rows,
        summary_tree=summary_tree,
        bank_id=adapter.bank_id,
    )
    _persist_balance_payload(session_id, response, canonical_df)

    return response


# ── Motor DataFrame reconstruction ──────────────────────────────────────────

_NON_MATURITY_TYPES = frozenset({
    "fixed_non_maturity", "variable_non_maturity",
    "static_position", "non-maturity",
})


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


# ── Lazy loading ─────────────────────────────────────────────────────────────

def _load_or_rebuild_summary(session_id: str) -> BalanceUploadResponse:
    summary_file = _summary_path(session_id)
    if summary_file.exists():
        payload = json.loads(summary_file.read_text(encoding="utf-8"))
        response = BalanceUploadResponse(**payload)

        rows = _read_positions_file(session_id)
        if rows is not None:
            response.summary_tree = _build_summary_tree(rows)
            summary_file.write_text(response.model_dump_json(indent=2), encoding="utf-8")

        return response

    xlsx_path = _latest_balance_file(session_id)
    filename = xlsx_path.name.removeprefix("balance__")
    return _parse_and_store_balance(session_id, filename=filename, xlsx_path=xlsx_path)


def _load_or_rebuild_positions(session_id: str) -> list[dict[str, Any]]:
    rows = _read_positions_file(session_id)
    if rows is not None:
        return rows

    _load_or_rebuild_summary(session_id)
    rows = _read_positions_file(session_id)
    if rows is not None:
        return rows

    raise HTTPException(status_code=404, detail="No balance uploaded for this session yet")
