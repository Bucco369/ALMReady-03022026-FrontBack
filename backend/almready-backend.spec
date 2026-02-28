# -*- mode: python ; coding: utf-8 -*-
#
# ALMReady backend – PyInstaller spec
#
# Build (run from repo root, NOT from backend/):
#
#   macOS arm64:
#     cd backend && ../.venv/bin/pyinstaller almready-backend.spec \
#       --distpath dist/macos-arm64
#
#   macOS x64 (on an Intel runner):
#     cd backend && ../.venv/bin/pyinstaller almready-backend.spec \
#       --distpath dist/macos-x64
#
#   Windows x64 (on a Windows runner):
#     cd backend && .venv\Scripts\pyinstaller almready-backend.spec ^
#       --distpath dist\windows-x64
#
# Output: dist/{platform}/almready-backend/almready-backend[.exe]
# This directory is referenced by tauri.conf.json as an externalBin sidecar.
#
# Build mode: --onedir (NOT --onefile).
# One-file mode re-extracts to a temp directory on every launch (3-5s penalty).
# One-directory mode keeps files on disk at install time – fast cold start.

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(SPECPATH)          # backend/
ROOT = HERE                    # spec lives in backend/

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(HERE / "sidecar_main.py")],
    pathex=[str(HERE)],        # makes `import app.*` and `import engine.*` work
    binaries=[],
    datas=[
        # Include the entire engine package (pure-Python sub-packages may be
        # missed by PyInstaller's import graph walker).
        (str(HERE / "engine"), "engine"),
        # Include app package data (schemas, config files, etc.)
        (str(HERE / "app"), "app"),
    ],
    hiddenimports=[
        # --- uvicorn: all entry-point plugins are selected at runtime via
        #     importlib.metadata; PyInstaller cannot see these statically. ---
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "uvicorn.logging",
        "uvicorn.middleware.proxy_headers",
        # --- h11 (HTTP/1.1 parser used by uvicorn) ---
        "h11",
        # --- engine.workers: passed to ProcessPoolExecutor; must be a
        #     top-level importable module in the frozen binary. ---
        "engine.workers",
        # --- orjson: Rust extension, may not be picked up automatically. ---
        "orjson",
        # --- pyarrow: several sub-modules imported dynamically. ---
        "pyarrow",
        "pyarrow._json",
        "pyarrow.vendored",
        "pyarrow.vendored.version",
        # --- numpy: platform C extension loaded at runtime. ---
        "numpy",
        "numpy.core._multiarray_umath",
        "numpy.core._multiarray_extras",
        # --- pandas: Cython extensions loaded lazily. ---
        "pandas",
        "pandas._libs.tslibs.np_datetime",
        "pandas._libs.tslibs.nattype",
        "pandas._libs.tslibs.timestamps",
        "pandas._libs.tslibs.offsets",
        "pandas._libs.tslibs.parsing",
        "pandas._libs.missing",
        "pandas._libs.interval",
        # --- openpyxl: cell writer and styles loaded via string imports. ---
        "openpyxl",
        "openpyxl.cell._writer",
        "openpyxl.styles.stylesheet",
        # --- multipart (FastAPI file upload dependency). ---
        "multipart",
        # --- starlette internals pulled in lazily. ---
        "starlette.middleware.cors",
        "starlette.middleware.base",
        "starlette.routing",
    ],
    excludes=[
        # matplotlib ships a Tk backend that pulls in the entire Tk/Tcl tree
        # (~30 MB).  We only use matplotlib for computation, not rendering.
        "tkinter",
        "_tkinter",
        "matplotlib.backends._backend_tk",
        "matplotlib.backends.backend_tkagg",
        # Jupyter / IPython not needed at runtime.
        "IPython",
        "jupyter",
        "notebook",
        # Test frameworks – not needed in the frozen binary.
        "pytest",
        "httpx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ---------------------------------------------------------------------------
# PYZ archive (pure-Python bytecode)
# ---------------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ---------------------------------------------------------------------------
# EXE
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # binaries go into COLLECT (one-directory mode)
    name="almready-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX can corrupt numpy/pandas C extensions
    # console=False hides the terminal window on Windows.  stdout is still
    # captured by the Tauri shell (pipe), so PORT:{port} is still received.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,          # None = native arch of the build machine
    codesign_identity=None,    # macOS signing handled by Tauri's build step
    entitlements_file=None,
)

# ---------------------------------------------------------------------------
# COLLECT (one-directory bundle)
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="almready-backend",
)
