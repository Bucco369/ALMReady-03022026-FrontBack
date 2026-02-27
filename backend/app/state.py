"""
Global mutable state shared across the application.

All modules access these via ``import app.state as state`` and then
``state._executor``, ``state._SESSIONS``, etc. so that rebinding in
the lifespan function is visible everywhere.
"""

from __future__ import annotations

import os
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

# In a packaged Tauri app the Tauri shell sets ALMREADY_DATA_DIR to the OS
# user-data directory (~/Library/Application Support/ALMReady on macOS,
# %APPDATA%\ALMReady on Windows).  In dev the variable is unset and we fall
# back to the repo-local backend/data/sessions/ directory as before.
_data_root = os.environ.get("ALMREADY_DATA_DIR")
SESSIONS_DIR = Path(_data_root) / "sessions" if _data_root else BASE_DIR / "data" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
