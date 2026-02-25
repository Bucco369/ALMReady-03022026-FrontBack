"""Balance data persistence: Parquet/JSON read/write and compat defaults."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from app.schemas import BalanceUploadResponse
from app.session import _positions_path, _summary_path
from app.parsers.transforms import _to_float


def _persist_balance_payload(
    session_id: str,
    response: BalanceUploadResponse,
    canonical_data: pd.DataFrame | list[dict[str, Any]],
) -> None:
    """Write summary JSON + canonical positions as Parquet.

    Accepts either a DataFrame (ZIP path, no reconstruction needed)
    or list-of-dicts (Excel path, backward compat).
    """
    _summary_path(session_id).write_text(response.model_dump_json(indent=2), encoding="utf-8")
    if isinstance(canonical_data, pd.DataFrame):
        canonical_data.to_parquet(_positions_path(session_id), index=False)
    else:
        pd.DataFrame(canonical_data).to_parquet(_positions_path(session_id), index=False)


def _apply_positions_compat_defaults(rows: list[dict[str, Any]]) -> bool:
    """Force deposits to maturity_years=0.0 and maturity_bucket='<1Y' (backward compat)."""
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


def _read_positions_file(session_id: str) -> list[dict[str, Any]] | None:
    """Read canonical positions from Parquet (new) or JSON (legacy)."""
    parquet_path = _positions_path(session_id)
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        return df.where(df.notna(), other=None).to_dict("records")

    # Legacy fallback: JSON file from before Parquet migration
    legacy_json = parquet_path.with_suffix(".json")
    if legacy_json.exists():
        rows = json.loads(legacy_json.read_text(encoding="utf-8"))
        _apply_positions_compat_defaults(rows)
        return rows

    return None
