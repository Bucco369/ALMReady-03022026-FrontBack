"""
Global mutable state shared across the application.

All modules access these via ``import app.state as state`` and then
``state._executor``, ``state._SESSIONS``, etc. so that rebinding in
the lifespan function is visible everywhere.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

# Persistent process pool – created at startup in main._lifespan().
_executor: ProcessPoolExecutor | None = None

# Hot cache of SessionMeta objects; populated lazily from disk.
_SESSIONS: dict = {}

# Per-session progress tracking (in-memory, ephemeral).
_upload_progress: dict[str, dict[str, Any]] = {}
_calc_progress: dict[str, dict[str, Any]] = {}

# Cached positions DataFrames for fast detail/contract queries.
# Populated lazily on first request; invalidated on upload/delete.
import pandas as pd
_positions_df_cache: dict[str, pd.DataFrame] = {}

# Disk paths
BASE_DIR = Path(__file__).resolve().parent.parent  # /backend/
SESSIONS_DIR = BASE_DIR / "data" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
