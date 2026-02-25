"""Path helpers and session persistence (read-through cache)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

import app.state as state
from app.schemas import SessionMeta


# ── Path helpers ────────────────────────────────────────────────────────────

def _session_dir(session_id: str) -> Path:
    path = state.SESSIONS_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_meta_path(session_id: str) -> Path:
    return state.SESSIONS_DIR / session_id / "meta.json"


def _positions_path(session_id: str) -> Path:
    return _session_dir(session_id) / "balance_positions.parquet"


def _summary_path(session_id: str) -> Path:
    return _session_dir(session_id) / "balance_summary.json"


def _motor_positions_path(session_id: str) -> Path:
    return _session_dir(session_id) / "motor_positions.parquet"


def _curves_summary_path(session_id: str) -> Path:
    return _session_dir(session_id) / "curves_summary.json"


def _curves_points_path(session_id: str) -> Path:
    return _session_dir(session_id) / "curves_points.json"


def _results_path(session_id: str) -> Path:
    return _session_dir(session_id) / "calculation_results.json"


def _calc_params_path(session_id: str) -> Path:
    return _session_dir(session_id) / "calculation_params.json"


def _chart_data_path(session_id: str) -> Path:
    return _session_dir(session_id) / "chart_data.json"


def _latest_uploaded_file(session_id: str, prefix: str, error_detail: str) -> Path:
    sdir = _session_dir(session_id)
    candidates = sorted(
        [
            p
            for p in sdir.iterdir()
            if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"} and p.name.startswith(prefix)
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise HTTPException(status_code=404, detail=error_detail)
    return candidates[0]


def _latest_balance_file(session_id: str) -> Path:
    return _latest_uploaded_file(
        session_id, "balance__", "No balance uploaded for this session yet",
    )


def _latest_curves_file(session_id: str) -> Path:
    return _latest_uploaded_file(
        session_id, "curves__", "No curves uploaded for this session yet",
    )


# ── Session persistence ─────────────────────────────────────────────────────

def _persist_session_meta(meta: SessionMeta) -> None:
    _session_dir(meta.session_id)
    _session_meta_path(meta.session_id).write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def _load_session_from_disk(session_id: str) -> SessionMeta | None:
    path = _session_meta_path(session_id)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = SessionMeta(**payload)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"Corrupted session metadata for {session_id}: {exc}")

    state._SESSIONS[session_id] = meta
    return meta


def _get_session_meta(session_id: str) -> SessionMeta | None:
    if session_id in state._SESSIONS:
        return state._SESSIONS[session_id]
    return _load_session_from_disk(session_id)


def _assert_session_exists(session_id: str) -> None:
    if _get_session_meta(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found. Create it first via POST /api/sessions")
