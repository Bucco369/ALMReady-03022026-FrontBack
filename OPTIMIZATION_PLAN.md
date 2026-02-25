# ALMReady ZIP Upload Pipeline — Deep Optimization Plan

## Context

**Repo:** `~/Desktop/ALMReady/ALMReady-03022026-FrontBack`
**Backend:** FastAPI + pandas engine in `backend/`
**Current perf:** 1,561,542 rows in ~4 minutes (240s)
**Target:** Under 60 seconds — use all CPU cores, eliminate redundant work
**Tests:** 186 passing — run from `backend/`: `.venv/bin/python -m pytest engine/tests/ -v`

## What Was Already Done (This Session)

1. **Parallel CSV reading** — `backend/engine/io/positions_pipeline.py` now has `parallel=N` parameter using `ThreadPoolExecutor`. Called from `balance_parser.py` with `parallel=min(specs, cpu_count)`.
2. **DataFrame-throughout** — `_canonicalize_motor_df()` returns `pd.DataFrame` instead of `list[dict]`. Eliminated the 1.5M-dict round-trip.
3. **Vectorized tree builder** — `_build_summary_tree_df()` uses `groupby` instead of 4×O(n) Python filter loops.
4. **Direct Parquet persistence** — `_persist_balance_payload()` accepts DataFrame, writes directly to Parquet without reconstructing from dicts.

These changes halved the time from ~8min to ~4min. The remaining 4 minutes are in **positions_reader.py** (CSV parsing + type conversion) and **_canonicalization.py** (classification + column construction).

---

## Architecture Quick Reference

```
HTTP POST /api/sessions/{sid}/balance/zip
  → balance.py:upload_balance_zip()          # FastAPI endpoint
    → asyncio.to_thread(_parse_zip_balance)  # offload to thread
      → balance_parser.py:_parse_zip_balance()
        → zipfile.extractall()               # extract to disk
        → positions_pipeline.py:load_positions_from_specs(parallel=N)
          → [PARALLEL] positions_reader.py:read_positions_tabular() × 10 files
            → _load_csv_table()              # encoding detect + pd.read_csv
            → read_positions_dataframe()     # column mapping + type conversion
        → pd.concat(frames)                  # merge all files
        → _canonicalization.py:_canonicalize_motor_df()
          → _classify_motor_df()             # 70 rules × vectorized
          → build canonical DataFrame        # 30+ columns
        → _tree_builder.py:_build_summary_tree_df()
        → _persistence.py:_persist_balance_payload()
```

### Key Files (read ALL of these before coding)

| File | Lines | Role |
|------|-------|------|
| `backend/engine/io/positions_reader.py` | ~742 | CSV reading, column mapping, type parsing — **THE MAIN BOTTLENECK** |
| `backend/engine/io/positions_pipeline.py` | ~260 | Multi-file orchestrator, parallel dispatch |
| `backend/app/parsers/_canonicalization.py` | ~387 | Motor→canonical classification + DataFrame construction |
| `backend/app/parsers/_tree_builder.py` | ~170 | Summary tree from DataFrame groupby |
| `backend/app/parsers/_persistence.py` | ~54 | Parquet/JSON persistence |
| `backend/app/parsers/balance_parser.py` | ~335 | ZIP upload orchestrator |
| `backend/app/routers/balance.py` | ~296 | HTTP endpoints |
| `backend/engine/config/bank_mapping_unicaja.py` | ~209 | Bank-specific column maps + SOURCE_SPECS |

---

## BOTTLENECK MAP: Where the 240 Seconds Go

```
CSV I/O + parsing .................. 120s  (50%)  ← positions_reader.py
  ├─ Type conversion (per-column) ... 70s
  ├─ Chunked read + concat .......... 30s
  └─ Encoding detection ............. 20s

String operations ................... 50s  (21%)  ← positions_reader.py
  ├─ _parse_numeric_column (14 passes) 40s
  └─ Repeated .astype(str) .......... 10s

Canonicalization .................... 40s  (17%)  ← _canonicalization.py
  ├─ Rule loop (70× str.contains) ... 20s
  ├─ Column construction ............ 15s
  └─ astype(object).where() .......... 5s

Tree building ....................... 15s   (6%)  ← _tree_builder.py (OK)
File I/O + overhead ................. 15s   (6%)
```

---

## THE FIXES — In Priority Order

### FIX 1: Rewrite `_parse_numeric_column` — SAVE ~40 SECONDS

**File:** `backend/engine/io/positions_reader.py`, lines 127-161
**Problem:** 14 separate `.str.X()` passes over the entire Series per numeric column. Called on 5 columns (notional, fixed_rate, spread, floor_rate, cap_rate) × all files.

**Current code (14 passes):**
```python
def _parse_numeric_column(series: pd.Series, *, allow_percent: bool) -> pd.Series:
    s = series.astype(str).str.strip()              # pass 1
    has_pct = s.str.contains("%", na=False)          # pass 2
    s = s.str.replace("%", "", regex=False)          # pass 3
    s = s.str.replace(" ", "", regex=False)          # pass 4
    has_comma = s.str.contains(",", na=False)        # pass 5
    has_dot = s.str.contains(".", na=False, ...)     # pass 6
    comma_last = s.str.rfind(",") > s.str.rfind(".") # pass 7-8
    # ... 6 more conditional .str.replace() passes
```

**Fix: Single-pass with numpy char operations + vectorized replace.**

Strategy:
1. Convert to `str` once: `s = series.astype(str).str.strip()`
2. Build a boolean mask for `%` presence in the same strip pass
3. Use `numpy.char` operations (faster than pandas `.str.`) for the character scanning
4. Collapse all comma/dot logic into a single `np.where` chain:
   - Detect format (European vs US vs comma-only) in ONE pass using `np.char.count`
   - Apply the right replacement in ONE vectorized operation
5. Final `pd.to_numeric(s, errors="coerce")` as before

**Target:** 14 passes → 3-4 passes. Each pass over 1.56M rows ≈ 3-5ms, so saving 10 passes = ~40 seconds across all files × all columns.

**Implementation outline:**
```python
def _parse_numeric_column(series: pd.Series, *, allow_percent: bool) -> pd.Series:
    arr = series.values.astype(str)  # numpy array, one copy

    # Single-pass: strip + detect + clean using numpy char ops
    arr = np.char.strip(arr)
    has_pct = np.char.find(arr, '%') >= 0
    arr = np.char.replace(arr, '%', '')
    arr = np.char.replace(arr, ' ', '')

    # Blank sentinel replacement
    blanks = np.isin(arr, ['nan', 'None', 'none', '<NA>', 'NaN', 'NaT', ''])

    # Comma/dot detection — single pass each
    n_comma = np.char.count(arr, ',')
    n_dot = np.char.count(arr, '.')
    has_both = (n_comma > 0) & (n_dot > 0)

    # Determine format and clean in one vectorized step
    # European (1.000,50): comma after last dot
    last_comma = np.array([s.rfind(',') for s in arr])  # unavoidable loop but on numpy
    last_dot = np.array([s.rfind('.') for s in arr])
    euro = has_both & (last_comma > last_dot)
    us = has_both & ~euro
    comma_only = (n_comma > 0) & (n_dot == 0)

    # Apply replacements using np.where to select the right transform
    # This is the tricky part — need to apply different transforms to different rows
    # Use pd.Series only for the .str operations on subsets
    s = pd.Series(arr, index=series.index)
    if euro.any():
        s[euro] = s[euro].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    if us.any():
        s[us] = s[us].str.replace(',', '', regex=False)
    if comma_only.any():
        s[comma_only] = s[comma_only].str.replace(',', '.', regex=False)

    s[blanks] = pd.NA
    parsed = pd.to_numeric(s, errors='coerce')

    if allow_percent and has_pct.any():
        parsed = parsed.where(~has_pct, parsed / 100.0)
    return parsed
```

**Key insight:** `numpy.char` functions are 3-10x faster than `pandas.str` because they avoid the pandas StringArray overhead. The `rfind` loop is unavoidable but operates on a numpy string array (much faster than pandas `.str.rfind`).

**Test:** All existing tests in `engine/tests/` must pass unchanged. The function signature doesn't change.

---

### FIX 2: Batch Type Conversions in `read_positions_dataframe` — SAVE ~20 SECONDS

**File:** `backend/engine/io/positions_reader.py`, lines 522-573
**Problem:** Type conversion happens column-by-column in a Python loop:

```python
for col in _DATE_COLUMNS:     # 3 iterations
    parsed = pd.to_datetime(df[col], ...)
    df[col] = parsed

for col in _NUMERIC_COLUMNS:  # 5 iterations
    parsed = _parse_numeric_column(df[col], ...)
    df[col] = parsed
```

Each `df[col] = parsed` triggers pandas dtype inference + copy. 8 columns × 1.56M rows × per-assignment overhead.

**Fix: Build all conversions, then assign in one batch.**

```python
# Batch all date conversions
date_updates = {}
for col in _DATE_COLUMNS:
    if col in df.columns:
        date_updates[col] = pd.to_datetime(df[col], dayfirst=date_dayfirst, errors="coerce")
df.update(pd.DataFrame(date_updates))  # single internal copy

# Batch all numeric conversions
numeric_updates = {}
for col in _NUMERIC_COLUMNS:
    if col in df.columns:
        numeric_updates[col] = _parse_numeric_column(df[col], allow_percent=(col in _PERCENT_COLUMNS))
df.update(pd.DataFrame(numeric_updates))  # single internal copy
```

Or even better — use `df.assign(**updates)` which returns a new DataFrame in one allocation.

**Alternative (more aggressive):** Pass `dtype=` hints to `pd.read_csv` so pandas parses types during C-level read instead of post-hoc Python conversion. This requires knowing column names ahead of time (we do — they're in `BANK_COLUMNS_MAP`).

```python
# In _load_csv_table, after resolving column names:
dtype_hints = {bank_col: 'float64' for bank_col, canon_col in bank_columns_map.items()
               if canon_col in _NUMERIC_COLUMNS}
df = pd.read_csv(path, ..., dtype=dtype_hints)
```

This eliminates post-hoc `_parse_numeric_column` for columns that are already clean floats (most Unicaja columns are semicolon-separated decimals with no comma/dot ambiguity).

---

### FIX 3: Increase CSV Chunk Size — SAVE ~8 SECONDS

**File:** `backend/engine/io/positions_reader.py`, line 358
**Problem:** `chunksize=50_000` creates ~31 chunks for 1.56M rows. Each chunk → append → callback → progress update. Final `pd.concat(chunks)` copies all data.

**Fix:** Change to `chunksize=200_000` (line 358). This creates ~8 chunks instead of 31. Fewer concat operations, fewer callback invocations, same progress granularity (progress bar updates 8 times per file instead of 31 — still smooth enough).

```python
# Line 358: change 50_000 → 200_000
chunksize=200_000,
```

**One-line change.** Test and verify progress bar still looks smooth on the frontend.

---

### FIX 4: Skip Encoding Detection When Encoding Is Known — SAVE ~5 SECONDS

**File:** `backend/engine/io/positions_reader.py`, lines 316-330 + 263-277
**Problem:** `_load_csv_table` tries up to 4 encodings sequentially. But for Unicaja, the encoding is ALWAYS `cp1252` (specified in SOURCE_SPECS). The function still tries `utf-8` first, fails, tries `utf-8-sig`, fails, then succeeds with `cp1252`.

**Fix:** In `_iter_csv_encodings` (line 263), when `preferred_encoding` is provided, try it FIRST and ONLY fall back if it fails:

```python
def _iter_csv_encodings(preferred_encoding: str | None) -> list[str]:
    if preferred_encoding:
        return [preferred_encoding]  # Trust the spec — don't waste time on others
    # ... existing fallback logic for unknown encodings
```

This is safe because Unicaja's SOURCE_SPECS explicitly declares `"encoding": "cp1252"`. If it's wrong, the read will fail and the error is clear. No silent fallback needed.

**Even better:** Since all 10 Unicaja CSVs share the same encoding, detect once on the first file and cache for the rest. Add to `_read_one_task` in `positions_pipeline.py`:

```python
# After first successful file read, cache the encoding
if not hasattr(mapping_module, '_detected_encoding'):
    mapping_module._detected_encoding = detected_enc
```

---

### FIX 5: Fix `_float_col` Double Parse in Canonicalization — SAVE ~3 SECONDS

**File:** `backend/app/parsers/_canonicalization.py`, lines 322-327
**Problem:** `_float_col` calls `pd.to_numeric` TWICE per column:

```python
def _float_col(name: str) -> pd.Series:
    return pd.to_numeric(motor_df[name], errors="coerce").where(
        pd.to_numeric(motor_df[name], errors="coerce").notna(), other=None  # PARSES TWICE!
    )
```

**Fix:**
```python
def _float_col(name: str) -> pd.Series:
    if name not in motor_df.columns:
        return pd.Series(None, index=motor_df.index, dtype="object")
    parsed = pd.to_numeric(motor_df[name], errors="coerce")
    return parsed.where(parsed.notna(), other=None)
```

Called on 4 columns (fixed_rate, spread, floor_rate, cap_rate) — each parse of 1.56M rows ≈ 50-100ms. Saving 4 redundant parses = ~200-400ms. Small but free.

---

### FIX 6: Cache Date Parsing in Canonicalization — SAVE ~2 SECONDS

**File:** `backend/app/parsers/_canonicalization.py`, lines 290-309
**Problem:** `maturity_date` is parsed by `pd.to_datetime` TWICE:
1. Line 298: `_col_to_iso("maturity_date")` — converts to ISO string
2. Line 303: `pd.to_datetime(motor_df["maturity_date"], errors="coerce")` — parses AGAIN for maturity_years

**Fix:** Parse once, reuse:
```python
# Parse all dates once
_date_cache = {}
for col_name in ("start_date", "maturity_date", "next_reprice_date"):
    if col_name in motor_df.columns:
        _date_cache[col_name] = pd.to_datetime(motor_df[col_name], errors="coerce")
    else:
        _date_cache[col_name] = pd.Series(pd.NaT, index=motor_df.index)

# ISO conversion uses cache
def _col_to_iso(col_name: str) -> pd.Series:
    dt = _date_cache[col_name]
    return dt.dt.strftime("%Y-%m-%d").where(dt.notna(), other=None)

# Maturity years uses same cache
mat_dt = _date_cache["maturity_date"]
mat_years = (mat_dt - pd.Timestamp(now)).dt.days / 365.25
```

---

### FIX 7: Eliminate `astype(object).where()` Copy — SAVE ~3 SECONDS

**File:** `backend/app/parsers/_canonicalization.py`, line 382
**Problem:** The final line before return does a full DataFrame copy:
```python
canonical_df = canonical_df.astype(object).where(canonical_df.notna(), other=None)
```

This converts ALL 30+ columns × 1.56M rows to Python objects, then replaces NaN with None.

**Fix:** Parquet handles NaN natively. The `None` conversion is only needed for JSON serialization (which happens later, in `_read_positions_file`). For the Parquet write path, skip it entirely:

```python
# Remove line 382 entirely.
# Parquet handles NaN/NaT → null automatically.
# The .where() None conversion happens later in _read_positions_file
# when converting Parquet → list[dict] for the JSON API response.
return canonical_df
```

Verify: Check that `_read_positions_file` in `_persistence.py` already does `.where(df.notna(), other=None)` on read (it does — line 44). So this is safe to remove from the write path.

---

### FIX 8: Switch ThreadPoolExecutor → ProcessPoolExecutor — SAVE ~15-30 SECONDS

**File:** `backend/engine/io/positions_pipeline.py`, lines 177-217
**Problem:** ThreadPoolExecutor doesn't actually parallelize because pandas `.str.X()` operations hold the GIL. Only the C-level `pd.read_csv` parsing releases it. The subsequent column mapping, type conversion, and validation are all GIL-bound Python.

**Fix:** Use `ProcessPoolExecutor` for true parallelism. Each worker process gets its own GIL.

**Tradeoff:** Each process copies the mapping_module + result DataFrame across process boundaries (pickle serialization). For 10 files with ~150K rows each, the serialization overhead is ~50-100ms per file. But the parallelism gain on an 8-core machine is 4-6x for the CPU-bound type conversion work.

**Implementation:**
```python
from concurrent.futures import ProcessPoolExecutor

# _read_one_task must be a top-level function (pickle requirement) — it already is.
# mapping_module must be picklable — it's a module, which IS picklable.

if parallel > 0 and len(file_tasks) > 1:
    workers = min(parallel, len(file_tasks))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        # ... same submit/as_completed pattern
```

**Caveat:** Progress callbacks DON'T work across processes (can't pickle closures). Two options:
1. Drop per-chunk progress in parallel mode — report per-file completion only
2. Use `multiprocessing.Queue` for progress — more complex but precise

Option 1 is simpler and acceptable: in parallel mode, progress jumps per-file instead of per-chunk. The total time is so much faster that smooth progress is less important.

**Test thoroughly:** Verify all 186 tests pass with `ProcessPoolExecutor`. Watch for:
- Pickle errors on mapping_module
- Memory usage (each process loads its own pandas)
- macOS `fork()` issues — may need `mp_context="spawn"`

---

### FIX 9: Pass `dtype` Hints to `pd.read_csv` — SAVE ~10-15 SECONDS

**File:** `backend/engine/io/positions_reader.py`, `_load_csv_table` (line 352+)
**Problem:** `pd.read_csv` infers dtypes by scanning data. Then `read_positions_dataframe` re-parses columns with `pd.to_numeric` and `pd.to_datetime`. Double work.

**Fix:** When the bank mapping specifies known numeric columns, pass `dtype` hints to `pd.read_csv`:

```python
# In read_positions_tabular or _load_csv_table:
# If we know which columns map to numeric canonical columns,
# tell pd.read_csv to parse them as float64 directly.

# Build dtype hints from bank mapping
dtype_hints = {}
for bank_col, canon_col in bank_columns_map.items():
    if canon_col in _NUMERIC_COLUMNS:
        dtype_hints[bank_col] = 'float64'

df = pd.read_csv(path, sep=delimiter, header=header_row,
                  encoding=enc, dtype=dtype_hints, ...)
```

**Caveat:** This only works if the bank's numeric columns are clean (no commas, no percent signs). For Unicaja, rates come as `2.50` (clean floats) and notionals come as `1000000.00` (clean floats). The semicolon delimiter means no comma/dot ambiguity. So `dtype='float64'` works directly and **eliminates the entire `_parse_numeric_column` call** for those columns.

For banks with European number formatting (commas as decimal), this won't work and the full `_parse_numeric_column` is still needed. Make this behavior opt-in via a flag in SOURCE_SPECS or the mapping module:

```python
# In bank_mapping_unicaja.py:
NUMERIC_COLUMNS_CLEAN = True  # numbers are already in standard float format
```

---

### FIX 10: Reduce `.astype(str)` Redundancy — SAVE ~5 SECONDS

**File:** `backend/engine/io/positions_reader.py`, scattered across multiple functions
**Problem:** The same column gets `.astype(str).str.strip()` called multiple times in different functions:
- `_normalise_categorical_column` (line 79): `raw.astype(str).str.strip().str.upper()`
- `_normalise_daycount_column` (line 104): `raw.astype(str).str.strip().str.upper()`
- `_parse_numeric_column` (line 129): `series.astype(str).str.strip()`
- `_check_required_not_null` (line 199): `df[col].astype(str).str.strip().eq("")`

**Fix:** Pre-convert ALL string columns once at the top of `read_positions_dataframe`, before any per-column processing:

```python
def read_positions_dataframe(df, mapping_module, ...):
    # ... rename columns ...

    # Pre-convert object columns to clean strings ONCE
    str_cols = df.select_dtypes(include='object').columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()
        df.loc[df[col].isin(['nan', 'None', '', '<NA>']), col] = pd.NA

    # Now all downstream functions can skip .astype(str).str.strip()
```

Then update `_normalise_categorical_column`, `_parse_numeric_column`, etc. to skip the `.astype(str).str.strip()` since it's already done.

---

## EXECUTION ORDER

Do these in order — each builds on the previous:

| Step | Fix | Est. Savings | Risk | Effort |
|------|-----|-------------|------|--------|
| 1 | FIX 5: `_float_col` double parse | 3s | Zero | 5 min |
| 2 | FIX 6: Cache date parsing | 2s | Zero | 10 min |
| 3 | FIX 7: Remove `astype(object).where()` | 3s | Low | 5 min |
| 4 | FIX 3: Increase chunk size 50K→200K | 8s | Zero | 1 min |
| 5 | FIX 4: Skip encoding detection | 5s | Low | 15 min |
| 6 | FIX 10: Pre-convert strings once | 5s | Medium | 30 min |
| 7 | FIX 1: Rewrite `_parse_numeric_column` | 40s | Medium | 1 hour |
| 8 | FIX 2: Batch type conversions | 20s | Medium | 45 min |
| 9 | FIX 9: dtype hints to `pd.read_csv` | 15s | Medium | 45 min |
| 10 | FIX 8: ProcessPoolExecutor | 15-30s | High | 2 hours |

**Steps 1-5:** Quick wins, zero/low risk, ~20 seconds saved. Do first, test, commit.
**Steps 6-9:** Medium effort, ~80 seconds saved. Core refactors in `positions_reader.py`.
**Step 10:** High effort/risk, biggest single gain. Do last after everything else is stable.

**Expected total savings: ~120-150 seconds → pipeline goes from 240s to ~90-120s**
With ProcessPoolExecutor (step 10): potentially ~60-80s.

---

## TESTING STRATEGY

After EVERY fix:
1. `cd backend && .venv/bin/python -m pytest engine/tests/ -v` — all 186 tests must pass
2. Manual ZIP upload test with the actual Unicaja data — verify:
   - Progress bar still works
   - Summary tree matches previous output
   - Balance details/contracts endpoints return same data
   - Motor Parquet file is identical (compare with `pandas.testing.assert_frame_equal`)

For FIX 8 (ProcessPoolExecutor):
- Test on macOS specifically (fork vs spawn)
- Monitor memory with `psutil` — each process adds ~200-300MB
- Verify no race conditions in progress reporting
- Test with `parallel=1` to verify sequential fallback still works

---

## FILES MODIFIED (Complete List)

| File | Fixes | What Changes |
|------|-------|-------------|
| `backend/engine/io/positions_reader.py` | 1,2,3,4,9,10 | Rewrite numeric parsing, batch conversions, chunk size, encoding, string pre-conversion |
| `backend/engine/io/positions_pipeline.py` | 8 | ProcessPoolExecutor, progress for multi-process |
| `backend/app/parsers/_canonicalization.py` | 5,6,7 | Cache dates, fix double parse, remove astype(object) |
| `backend/engine/config/bank_mapping_unicaja.py` | 9 | Add `NUMERIC_COLUMNS_CLEAN = True` flag |

**Files NOT modified:** `balance_parser.py`, `_tree_builder.py`, `_persistence.py`, `balance.py`, `filters.py`, `transforms.py` — these are already optimized from the previous session.
