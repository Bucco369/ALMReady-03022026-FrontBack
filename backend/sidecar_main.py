"""
ALMReady backend – PyInstaller / Tauri sidecar entry point.

This module is the entry point for the frozen binary that Tauri spawns as a
background sidecar process.  It is NOT used during normal development
(uvicorn app.main:app --reload is used instead).

Startup protocol:
  1. multiprocessing.freeze_support() is called first – mandatory for
     ProcessPoolExecutor workers inside a frozen executable on Windows.
  2. A free OS port is discovered by binding to 127.0.0.1:0.
  3. "PORT:{port}" is printed to stdout (flushed) so the Tauri Rust shell can
     read it and know where to proxy health-check polling.
  4. uvicorn starts the FastAPI app on that port.  The lifespan startup
     (ProcessPoolExecutor warm-up) completes, then /api/health returns 200.
     The Tauri shell polls until healthy, then shows the app window.

Environment variables set by the Tauri shell before spawning this process:
  ALMREADY_DATA_DIR   – OS user-data directory for session persistence
  ALMREADY_CORS_ORIGINS – Tauri webview origins for CORS whitelist
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import sys

# ── Static import so PyInstaller walks the full dependency tree ──────────────
# uvicorn.run("app.main:app", ...) is a string-based import that PyInstaller
# cannot follow — fastapi, starlette, pydantic etc. would be absent from the
# frozen bundle.  Importing the app object here makes PyInstaller bundle every
# transitive dependency of app.main (fastapi, starlette, all routers, engine…).
# We pass the object (not the string) to uvicorn.run() below.
from app.main import app as _fastapi_app  # noqa: E402


def _find_free_port() -> int:
    """Bind to port 0, let the OS assign a free port, return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    # Ensure the backend package is importable when running from the frozen
    # one-directory bundle (the executable lives inside the bundle directory
    # which also contains app/ and engine/).
    bundle_dir = os.path.dirname(sys.executable)
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

    port = _find_free_port()

    # Signal the Tauri shell with the chosen port before uvicorn blocks.
    print(f"PORT:{port}", flush=True)

    import uvicorn

    # Pass the app object directly (not as a string) so uvicorn does not
    # attempt a dynamic string import inside the frozen binary.
    uvicorn.run(
        _fastapi_app,
        host="127.0.0.1",
        port=port,
        # workers=1 is required: our existing ProcessPoolExecutor inside the
        # FastAPI lifespan handles parallelism.  uvicorn multi-worker mode uses
        # a separate multiprocessing strategy that conflicts with frozen apps.
        workers=1,
        loop="asyncio",
        # Suppress access log in the sidecar – the backend's own middleware
        # already logs requests.
        access_log=False,
    )


if __name__ == "__main__":
    # freeze_support() MUST be the very first call in the __main__ block.
    # Without it, ProcessPoolExecutor worker processes spawned inside a frozen
    # binary silently hang on Windows (the worker re-executes the frozen exe
    # without this guard and enters an infinite spawn loop).
    multiprocessing.freeze_support()
    main()
