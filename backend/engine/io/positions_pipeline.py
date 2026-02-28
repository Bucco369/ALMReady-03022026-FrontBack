from __future__ import annotations

import multiprocessing as mp
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from engine.io._utils import (
    mapping_attr as _mapping_attr,
    resolve_glob_matches as _resolve_glob_matches,
    to_sequence as _to_sequence,
)
from engine.io.positions_reader import read_positions_tabular


def _init_worker() -> None:
    """Ensure spawned child processes can import project modules."""
    import sys
    backend_dir = str(Path(__file__).resolve().parent.parent.parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _make_chunk_callback(
    on_progress: Callable[[int, int], None],
    base_bytes: int,
    file_bytes: int,
    total_bytes: int,
    est_rows: float,
) -> Callable[[int], None]:
    """Create a per-chunk callback that maps rows-read → bytes-processed."""

    def _on_rows(rows_so_far: int) -> None:
        frac = min(rows_so_far / est_rows, 0.99)
        current = base_bytes + int(frac * file_bytes)
        on_progress(current, total_bytes)

    return _on_rows


class _ThreadSafeProgress:
    """Thread-safe byte counter for parallel file reading progress."""

    def __init__(self, total_bytes: int, on_progress: Callable[[int, int], None]):
        self._lock = threading.Lock()
        self._completed_bytes = 0
        self._inflight: dict[int, int] = {}  # task_id → current bytes
        self._total = total_bytes
        self._on_progress = on_progress

    def make_callback(self, task_id: int, file_bytes: int, est_rows: float) -> Callable[[int], None]:
        def _on_rows(rows_so_far: int) -> None:
            frac = min(rows_so_far / est_rows, 0.99)
            with self._lock:
                self._inflight[task_id] = int(frac * file_bytes)
                current = self._completed_bytes + sum(self._inflight.values())
                self._on_progress(current, self._total)
        return _on_rows

    def mark_complete(self, task_id: int, file_bytes: int) -> None:
        with self._lock:
            self._inflight.pop(task_id, None)
            self._completed_bytes += file_bytes
            self._on_progress(self._completed_bytes, self._total)


def _read_one_task_mp(
    task_id: int,
    raw_spec: dict[str, Any],
    source_file: Path,
    effective_sheets: list,
    module_name: str,
    row_cb: Callable[[int], None] | None,
) -> list[pd.DataFrame]:
    """ProcessPoolExecutor wrapper: imports mapping module by name then delegates."""
    import importlib
    mapping_module = importlib.import_module(module_name)
    return _read_one_task(task_id, raw_spec, source_file, effective_sheets, mapping_module, row_cb)


def _read_one_task_to_parquet(
    task_id: int,
    raw_spec: dict[str, Any],
    source_file: Path,
    effective_sheets: list,
    module_name: str,
    output_dir: str,
) -> list[str]:
    """Worker that writes results to Parquet files instead of returning DataFrames.

    Avoids pickle serialization of large DataFrames across process boundaries.
    Returns a list of lightweight file paths (strings) instead.
    """
    import importlib
    mapping_module = importlib.import_module(module_name)
    frames = _read_one_task(task_id, raw_spec, source_file, effective_sheets, mapping_module, None)

    paths: list[str] = []
    for i, df in enumerate(frames):
        out = Path(output_dir) / f"task_{task_id}_{i}.parquet"
        df.to_parquet(out, engine="pyarrow", index=False)
        paths.append(str(out))
    return paths


def _read_one_task(
    task_id: int,
    raw_spec: Mapping[str, Any],
    source_file: Path,
    effective_sheets: list,
    mapping_module: Any,
    row_cb: Callable[[int], None] | None,
) -> list[pd.DataFrame]:
    """Read a single file task (one spec + one file + its sheets). Thread-safe."""
    spec_name = str(raw_spec.get("name", raw_spec.get("pattern", "")))
    defaults = raw_spec.get("defaults")
    file_type = str(raw_spec.get("file_type", raw_spec.get("kind", "auto")))

    results: list[pd.DataFrame] = []
    for sheet in effective_sheets:
        df = read_positions_tabular(
            path=source_file,
            mapping_module=mapping_module,
            file_type=file_type,
            sheet_name=sheet,
            delimiter=raw_spec.get("delimiter"),
            encoding=raw_spec.get("encoding"),
            decimal=raw_spec.get("decimal", "."),
            header_row=raw_spec.get("header_row", 0),
            header_token=raw_spec.get("header_token"),
            row_kind_column=raw_spec.get("row_kind_column"),
            include_row_kinds=raw_spec.get("include_row_kinds"),
            drop_row_kind_column=bool(raw_spec.get("drop_row_kind_column", True)),
            canonical_defaults_override=defaults,
            source_row_column="source_row",
            reset_index=True,
            on_rows_read=row_cb,
        )

        df["source_spec"] = spec_name
        df["source_file"] = str(source_file)
        if file_type.lower() == "csv":
            df["source_sheet"] = pd.NA
        else:
            df["source_sheet"] = sheet

        if "source_bank" in raw_spec:
            df["source_bank"] = raw_spec.get("source_bank")
        if "source_contract_type" in raw_spec:
            df["source_contract_type"] = raw_spec.get("source_contract_type")

        results.append(df)
    return results


def load_positions_from_specs(
    root_path: str | Path,
    mapping_module: Any,
    *,
    source_specs: Sequence[Mapping[str, Any]] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    parallel: int = 0,
    executor: ProcessPoolExecutor | None = None,
) -> pd.DataFrame:
    """
    Loads and canonicalises positions from multiple files using declarative SOURCE_SPECS.

    Progress callback receives (bytes_processed, total_bytes) — weighted by
    file size so large files move the bar proportionally more than small ones.
    Within each CSV file, progress updates every 50K rows via chunked reading.

    When parallel > 0, uses a ProcessPoolExecutor to read files concurrently.
    If *executor* is provided (e.g. the pre-warmed pool from the app lifespan),
    tasks are submitted to it — avoiding the overhead of spawning new worker
    processes (critical in PyInstaller frozen binaries where each new process
    re-imports the entire application stack).
    """

    base_path = Path(root_path)
    if not base_path.exists():
        raise FileNotFoundError(f"root_path for positions does not exist: {base_path}")

    specs = (
        list(source_specs)
        if source_specs is not None
        else list(_mapping_attr(mapping_module, "SOURCE_SPECS"))
    )
    if not specs:
        raise ValueError("SOURCE_SPECS is empty: define at least one source.")

    # ── Pre-scan: resolve all files and compute total bytes ──────────────
    file_tasks: list[tuple[Mapping[str, Any], Path, list]] = []
    total_bytes = 0

    for idx, raw_spec in enumerate(specs, start=1):
        if not isinstance(raw_spec, Mapping):
            raise ValueError(f"SOURCE_SPECS[{idx}] must be Mapping, received: {type(raw_spec)}")

        pattern = raw_spec.get("pattern")
        if not pattern:
            raise ValueError(f"SOURCE_SPECS[{idx}] missing 'pattern'.")

        required = bool(raw_spec.get("required", True))
        file_type = str(raw_spec.get("file_type", raw_spec.get("kind", "auto")))
        sheet_names = raw_spec.get("sheet_names", raw_spec.get("sheet_name", 0))

        matches = _resolve_glob_matches(base_path, str(pattern))
        if not matches:
            if required:
                raise FileNotFoundError(
                    f"No file found for pattern='{pattern}' in {base_path}"
                )
            continue

        for source_file in matches:
            if file_type.lower() == "csv":
                effective_sheets = [0]
            else:
                effective_sheets = _to_sequence(sheet_names)

            file_tasks.append((raw_spec, source_file, effective_sheets))
            total_bytes += source_file.stat().st_size

    # ── Parallel path ────────────────────────────────────────────────────
    # ProcessPoolExecutor bypasses the GIL, giving true parallelism for
    # CPU-bound type conversion and string processing.  Workers write results
    # as Parquet temp files instead of returning DataFrames via pickle,
    # avoiding ~15s of serialization overhead on 1.5M+ row datasets.
    #
    # When an external *executor* is supplied (e.g. the pre-warmed pool from
    # the FastAPI lifespan), we submit tasks to it directly.  This avoids
    # spawning a second set of worker processes — critical in PyInstaller
    # frozen binaries where each spawn re-executes the entire frozen exe,
    # re-importing the full app stack (10-20s overhead + 200MB per worker).
    if parallel > 0 and len(file_tasks) > 1:
        import tempfile, shutil

        workers = min(parallel, len(file_tasks))
        module_name = mapping_module.__name__
        tmpdir = tempfile.mkdtemp(prefix="alm_parallel_")

        # Decide whether to use the caller's executor or create a fresh one.
        own_pool = executor is None
        pool: ProcessPoolExecutor | None = None

        try:
            ordered_paths: list[tuple[int, list[str]]] = []
            completed_bytes = 0

            if own_pool:
                ctx = mp.get_context("spawn")  # safe on macOS (avoids fork-safety issues)
                pool = ProcessPoolExecutor(
                    max_workers=workers,
                    mp_context=ctx,
                    initializer=_init_worker,
                )
            else:
                pool = executor

            futures = {}
            for task_id, (raw_spec, source_file, effective_sheets) in enumerate(file_tasks):
                file_bytes = source_file.stat().st_size
                fut = pool.submit(
                    _read_one_task_to_parquet,
                    task_id, dict(raw_spec), source_file, effective_sheets,
                    module_name, tmpdir,
                )
                futures[fut] = (task_id, file_bytes)

            for fut in as_completed(futures):
                task_id, file_bytes = futures[fut]
                parquet_paths = fut.result()  # lightweight list of strings
                ordered_paths.append((task_id, parquet_paths))
                completed_bytes += file_bytes
                if on_progress and total_bytes > 0:
                    on_progress(completed_bytes, total_bytes)

            # Read temp Parquet files in original spec order for deterministic concat
            ordered_paths.sort(key=lambda x: x[0])
            frames = [
                pd.read_parquet(p)
                for _, paths in ordered_paths
                for p in paths
            ]
        finally:
            if own_pool and pool is not None:
                pool.shutdown(wait=True)
            shutil.rmtree(tmpdir, ignore_errors=True)

        if not frames:
            raise ValueError("No positions loaded from SOURCE_SPECS.")
        return pd.concat(frames, ignore_index=True)

    # ── Sequential path (original behavior) ──────────────────────────────
    frames: list[pd.DataFrame] = []
    processed_bytes = 0
    bytes_per_row = 250.0

    for raw_spec, source_file, effective_sheets in file_tasks:
        file_bytes = source_file.stat().st_size

        row_cb = None
        if on_progress and total_bytes > 0:
            est_rows = max(file_bytes / bytes_per_row, 1)
            row_cb = _make_chunk_callback(
                on_progress, processed_bytes, file_bytes, total_bytes, est_rows,
            )

        task_frames = _read_one_task(
            0, raw_spec, source_file, effective_sheets, mapping_module, row_cb,
        )
        frames.extend(task_frames)

        # Self-adjust bytes-per-row estimate from actual data.
        for df in task_frames:
            if len(df) > 100:
                bytes_per_row = file_bytes / len(df)

        processed_bytes += file_bytes
        if on_progress and total_bytes > 0:
            on_progress(processed_bytes, total_bytes)

    if not frames:
        raise ValueError("No positions loaded from SOURCE_SPECS.")

    return pd.concat(frames, ignore_index=True)
