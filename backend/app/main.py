"""
ALMReady Backend – FastAPI application entry point.

Startup: uvicorn app.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, wait as _cf_wait
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

import app.state as state
from app.routers import balance, calculate, curves, sessions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger("engine")


SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "7"))
_CLEANUP_INTERVAL_HOURS = 6


def _cleanup_old_sessions(max_age_days: int | None = None) -> None:
    """Remove session directories older than *max_age_days* from disk."""
    if max_age_days is None:
        max_age_days = SESSION_TTL_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    purged = 0
    for entry in state.SESSIONS_DIR.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        try:
            if meta_path.exists():
                created = datetime.fromisoformat(
                    json.loads(meta_path.read_text(encoding="utf-8"))["created_at"]
                )
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if created >= cutoff:
                    continue
            shutil.rmtree(entry)
            state._positions_df_cache.pop(entry.name, None)
            purged += 1
        except Exception:
            _log.debug("Skipping cleanup of %s", entry.name, exc_info=True)
    if purged:
        _log.info("Purged %d session(s) older than %d days", purged, max_age_days)


async def _periodic_cleanup() -> None:
    """Run session cleanup every _CLEANUP_INTERVAL_HOURS while the server is up."""
    import asyncio

    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_HOURS * 3600)
        try:
            _cleanup_old_sessions()
        except Exception:
            _log.warning("Periodic session cleanup failed", exc_info=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: purge stale sessions, pre-warm process pool, schedule cleanup."""
    import asyncio

    import engine.workers as _workers

    _cleanup_old_sessions()

    n_workers = os.cpu_count() or 1
    state._executor = ProcessPoolExecutor(max_workers=n_workers)
    _cf_wait([state._executor.submit(_workers.warmup) for _ in range(n_workers)])

    cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
    cleanup_task.cancel()
    state._executor.shutdown(wait=True)
    state._executor = None


app = FastAPI(lifespan=_lifespan)


class _RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        dt = (time.perf_counter() - t0) * 1000
        if request.url.path.startswith("/api/"):
            _log.info(
                "%s %s → %d (%.0f ms)",
                request.method, request.url.path, response.status_code, dt,
            )
        return response


app.add_middleware(_RequestLoggingMiddleware)

# ALMREADY_CORS_ORIGINS: comma-separated extra origins injected by the Tauri
# shell at runtime (e.g. "tauri://localhost,https://tauri.localhost").
_extra_origins = [
    o.strip()
    for o in os.environ.get("ALMREADY_CORS_ORIGINS", "").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # Tauri webview origins (macOS and Windows respectively)
        "tauri://localhost",
        "https://tauri.localhost",
        *_extra_origins,
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(balance.router)
app.include_router(curves.router)
app.include_router(calculate.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
