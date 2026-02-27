"""Balance data persistence: Parquet/JSON read/write and compat defaults."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

import app.state as state
from app.schemas import BalanceUploadResponse
from app.session import _positions_path, _summary_path
from app.parsers.transforms import _to_float


# ── Column pruning: only the columns needed for detail/contract queries ────
_QUERY_COLUMNS = [
    "include_in_balance_tree", "side", "subcategory_id", "subcategoria_ui",
    "categoria_ui", "group", "currency", "rate_type", "counterparty",
    "business_segment", "strategic_segment", "book_value_def",
    "maturity_bucket", "remuneration_bucket",
    "amount", "rate_display", "maturity_years",
    "contract_id", "sheet",
]


def _persist_balance_payload(
    session_id: str,
    response: BalanceUploadResponse,
    canonical_data: pd.DataFrame | list[dict[str, Any]],
) -> None:
    """Write summary JSON + canonical positions as Parquet.

    Accepts either a DataFrame (ZIP path, no reconstruction needed)
    or list-of-dicts (Excel path, backward compat).
    Also primes the in-memory DataFrame cache to avoid re-reading Parquet.
    """
    _summary_path(session_id).write_text(response.model_dump_json(indent=2), encoding="utf-8")
    if isinstance(canonical_data, pd.DataFrame):
        canonical_data.to_parquet(_positions_path(session_id), index=False)
        _prime_positions_cache(session_id, canonical_data)
    else:
        df = pd.DataFrame(canonical_data)
        df.to_parquet(_positions_path(session_id), index=False)
        _prime_positions_cache(session_id, df)


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


# ── DataFrame cache (Steps 1 + 3: caching + column pruning) ──────────────


def _recompute_remuneration_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute remuneration_bucket from rate_display if values look stale.

    Detects Parquet files written before the decimal→percentage fix and
    recomputes the column in-place (~2ms for 1.5M rows).
    """
    if "rate_display" not in df.columns:
        return df
    if "remuneration_bucket" not in df.columns:
        return df
    # Heuristic: if the column has <= 2 unique non-null values, it was
    # likely computed with the old (broken) decimal-scale bucketing.
    nunique = df["remuneration_bucket"].dropna().nunique()
    if nunique > 2:
        return df

    rate = df["rate_display"]
    abs_rate = rate.abs() * 100  # decimal → percentage points
    import numpy as np
    bucket = pd.Series("-", index=df.index, dtype="object")
    bucket = bucket.where(rate.isna(), "5%+")
    bucket = bucket.where(rate.isna() | (abs_rate > 5), "4-5%")
    bucket = bucket.where(rate.isna() | (abs_rate > 4), "3-4%")
    bucket = bucket.where(rate.isna() | (abs_rate > 3), "2-3%")
    bucket = bucket.where(rate.isna() | (abs_rate > 2), "1-2%")
    bucket = bucket.where(rate.isna() | (abs_rate > 1), "0-1%")
    bucket = bucket.where(rate.isna() | (abs_rate > 0), "0%")
    df["remuneration_bucket"] = bucket
    return df


def _load_positions_df(session_id: str) -> pd.DataFrame | None:
    """Load canonical positions as a cached, column-pruned DataFrame.

    First request reads Parquet (only the columns needed for queries).
    Subsequent requests return the cached DataFrame instantly.
    """
    cached = state._positions_df_cache.get(session_id)
    if cached is not None:
        return cached

    parquet_path = _positions_path(session_id)
    if parquet_path.exists():
        # Column pruning: read only needed columns from Parquet metadata
        available = set(pq.read_schema(parquet_path).names)
        cols = [c for c in _QUERY_COLUMNS if c in available]
        df = pd.read_parquet(parquet_path, columns=cols if cols else None)
        df = _recompute_remuneration_bucket(df)
        state._positions_df_cache[session_id] = df
        return df

    # Legacy fallback: JSON file from before Parquet migration
    legacy_json = parquet_path.with_suffix(".json")
    if legacy_json.exists():
        rows = json.loads(legacy_json.read_text(encoding="utf-8"))
        _apply_positions_compat_defaults(rows)
        df = pd.DataFrame(rows)
        cols = [c for c in _QUERY_COLUMNS if c in df.columns]
        df = df[cols] if cols else df
        state._positions_df_cache[session_id] = df
        return df

    return None


def _invalidate_positions_cache(session_id: str) -> None:
    """Remove cached DataFrame for a session (call on delete/re-upload)."""
    state._positions_df_cache.pop(session_id, None)


def _prime_positions_cache(session_id: str, df: pd.DataFrame) -> None:
    """Prime the cache from a DataFrame already in memory (avoids Parquet re-read)."""
    cols = [c for c in _QUERY_COLUMNS if c in df.columns]
    state._positions_df_cache[session_id] = df[cols].copy()
