"""Balance upload, summary, details, contracts, progress, and delete routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

import app.state as state
from app.schemas import (
    BalanceContract,
    BalanceContractsResponse,
    BalanceDetailsResponse,
    BalanceUploadResponse,
)
from app.session import (
    _assert_session_exists,
    _calc_params_path,
    _motor_positions_path,
    _positions_path,
    _results_path,
    _session_dir,
    _summary_path,
)
from app.parsers.balance_parser import (
    _build_summary_tree,
    _load_or_rebuild_positions,
    _load_or_rebuild_summary,
    _parse_and_store_balance,
    _parse_zip_balance,
    _persist_balance_payload,
)
from app.parsers.transforms import _to_float, _to_text
from app.filters import (
    _aggregate_groups,
    _aggregate_totals,
    _apply_filters,
    _build_facets,
)

router = APIRouter()


@router.delete("/api/sessions/{session_id}/balance")
def delete_balance(session_id: str) -> dict[str, str]:
    _assert_session_exists(session_id)
    sdir = _session_dir(session_id)
    deleted: list[str] = []
    motor_parquet = _motor_positions_path(session_id)
    motor_json_legacy = motor_parquet.with_suffix(".json")
    for p in [_summary_path(session_id), _positions_path(session_id), motor_parquet, motor_json_legacy]:
        if p.exists():
            p.unlink()
            deleted.append(p.name)
    for p in sdir.iterdir():
        if p.is_file() and p.name.startswith("balance__"):
            p.unlink()
            deleted.append(p.name)
    for p in [_results_path(session_id), _calc_params_path(session_id)]:
        if p.exists():
            p.unlink()
            deleted.append(p.name)
    return {"status": "ok", "deleted": ", ".join(deleted) if deleted else "nothing to delete"}


@router.post("/api/sessions/{session_id}/balance", response_model=BalanceUploadResponse)
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


@router.post("/api/sessions/{session_id}/balance/zip", response_model=BalanceUploadResponse)
async def upload_balance_zip(session_id: str, file: UploadFile = File(...)) -> BalanceUploadResponse:
    import asyncio

    _assert_session_exists(session_id)

    raw_filename = file.filename or "balance.zip"
    if not raw_filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported for this endpoint")

    safe_filename = Path(raw_filename).name
    sdir = _session_dir(session_id)
    zip_path = sdir / f"balance__{safe_filename}"
    content = await file.read()
    zip_path.write_bytes(content)

    # Run in thread so the event loop stays responsive for progress polling
    sheet_summaries, sample_rows, canonical_rows = await asyncio.to_thread(
        _parse_zip_balance, session_id, zip_path,
    )

    summary_tree = _build_summary_tree(canonical_rows)
    response = BalanceUploadResponse(
        session_id=session_id,
        filename=safe_filename,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        sheets=sheet_summaries,
        sample_rows=sample_rows,
        summary_tree=summary_tree,
    )

    _persist_balance_payload(session_id, response, canonical_rows)
    state._upload_progress.pop(session_id, None)
    return response


@router.get("/api/sessions/{session_id}/upload-progress")
def get_upload_progress(session_id: str):
    progress = state._upload_progress.get(session_id)
    if progress is None:
        return {"phase": "idle", "step": 0, "total": 0, "pct": 0, "phase_label": ""}
    step = progress.get("step", 0)
    total = progress.get("total", 0)
    phase = progress.get("phase", "parsing")

    _PHASE_LABELS = {
        "parsing": "Parsing positions…",
        "persisting": "Saving data…",
        "canonicalizing": "Building aggregates…",
    }
    phase_label = _PHASE_LABELS.get(phase, "Processing…")

    if phase == "parsing" and total > 0:
        pct = 5 + round((step / total) * 65)
    elif phase == "persisting" and total > 0:
        pct = 70 + round((step / total) * 10)
    elif phase == "persisting":
        pct = 75
    elif phase == "canonicalizing" and total > 0:
        pct = 80 + round((step / total) * 15)
    elif phase == "canonicalizing":
        pct = 88
    else:
        pct = 5

    return {"phase": phase, "step": step, "total": total, "pct": pct, "phase_label": phase_label}


@router.get("/api/sessions/{session_id}/balance/summary", response_model=BalanceUploadResponse)
def get_balance_summary(session_id: str) -> BalanceUploadResponse:
    _assert_session_exists(session_id)
    return _load_or_rebuild_summary(session_id)


@router.get("/api/sessions/{session_id}/balance/details", response_model=BalanceDetailsResponse)
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


@router.get("/api/sessions/{session_id}/balance/contracts", response_model=BalanceContractsResponse)
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
