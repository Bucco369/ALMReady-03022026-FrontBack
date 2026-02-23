# ZIP Upload → Parsing → Persist Optimization Plan

## Context for New Conversation

This document describes the performance bottlenecks in the ZIP balance upload
pipeline and a concrete plan to fix them. Paste this into a fresh conversation
so Claude can execute the changes.

**Codebase**: ALMReady (FastAPI backend + React frontend)
**Key files**:
- `backend/app/main.py` — `_parse_zip_balance()` (line ~1292), `_canonicalize_motor_row()` (line ~1007), `_serialize_value_for_json()` (line ~687)
- `backend/almready/io/positions_reader.py` — `_load_csv_table()` (line ~339), `read_positions_dataframe()` (line ~439)
- `backend/almready/io/positions_pipeline.py` — `load_positions_from_specs()` (line ~33)
- `backend/almready/config/bank_mapping_unicaja.py` — `SOURCE_SPECS` (10 CSV specs)

**Scale** (div4 = 1/4 of full bank data, already downsampled):
| File | Size | Lines | Data rows |
|------|------|-------|-----------|
| Non-maturity.csv | 398 MB | 979K | ~980K |
| Variable annuity.csv | 176 MB | 323K | ~323K |
| Fixed bullet.csv | 74 MB | 165K | ~165K |
| Fixed annuity.csv | 40 MB | 87K | ~87K |
| **Total** | **~692 MB** | **~1.56M** | **~1.56M rows** |

The full bank balance (no downsampling) would be ~4× this: **~6M rows, ~2.8 GB of CSVs**.

---

## Current Pipeline (Sequential, Synchronous)

```
upload_balance_zip (FastAPI endpoint, async but blocks event loop)
  └─ _parse_zip_balance()                      [SYNC, blocks event loop]
       ├─ 1. zipfile.extractall()              ~2s
       ├─ 2. load_positions_from_specs()       ~5-10 min  ← MAIN BOTTLENECK
       │    └─ for each spec (8 CSV files, sequential):
       │         └─ read_positions_tabular()
       │              ├─ _load_csv_table()
       │              │    ├─ path.read_text()           ← READS ENTIRE FILE INTO MEMORY AS STRING
       │              │    ├─ _find_header_row_from_lines()  ← scans lines list for "Identifier"
       │              │    └─ pd.read_csv()              ← RE-READS THE SAME FILE FROM DISK
       │              ├─ _apply_row_kind_filter()        (fast, vectorised)
       │              └─ read_positions_dataframe()
       │                   ├─ df.dropna(how="all").copy()
       │                   ├─ df.rename(columns=rename_map)
       │                   ├─ df[keep_columns].copy()    ← 3rd full copy of data
       │                   ├─ for col in DATE_COLUMNS:
       │                   │    df[col].apply(_parse_date)    ← Python-level row iteration
       │                   ├─ for col in NUMERIC_COLUMNS:
       │                   │    df[col].apply(_parse_number)  ← Python-level row iteration
       │                   ├─ _normalise_categorical_column() ← Python for-loop per row
       │                   ├─ _normalise_daycount_column()    ← Python for-loop per row
       │                   └─ _check_required_not_null()      ← .apply(_is_blank_cell) per col
       │
       ├─ 3. motor_df.to_dict(orient="records") → motor_records     ~30s
       │    └─ for rec in motor_records:                             ~2-5 min
       │         for key, val in rec.items():
       │              rec[key] = _serialize_value_for_json(val)      ← 1.5M × 20 cols = 30M calls
       │    └─ json.dumps(motor_records, indent=2)                  ~30s-1min (writes 500MB+ JSON)
       │    └─ path.write_text(json_string)                         ~5-10s
       │
       └─ 4. for rec in motor_records:                              ~2-5 min
              canonical_rows.append(_canonicalize_motor_row(rec))    ← 1.5M Python function calls
```

**Total estimated time: 10-20+ minutes** for div4 data. Full bank data: 40-80+ minutes.

---

## Bottleneck Analysis (Ordered by Impact)

### B1. DOUBLE FILE READ in `_load_csv_table()` [HIGH]
**File**: `positions_reader.py:339-395`

The function reads the entire CSV **twice**:
1. `path.read_text(encoding=enc).splitlines()` — loads full file into a Python string, then splits into a list of strings (2× memory of file size)
2. `pd.read_csv(path, ...)` — reads the same file from disk again into a DataFrame

For `Non-maturity.csv` (398 MB), step 1 allocates ~800 MB (string + lines list) just to find which line number contains "Identifier" (always line 9-10 in these files). Then step 2 allocates another ~1-2 GB for the DataFrame.

**Peak memory for one file**: ~3 GB just for a 398 MB CSV.

**Fix**: Read only the first N lines (e.g., 50) to find the header token, then call `pd.read_csv` with `skiprows` and `header=0`. Never load the full file as a string.

### B2. Python-level row iteration for parsing [HIGH]
**File**: `positions_reader.py:533-550`

Date and numeric columns are parsed via `.apply(lambda)` which runs a Python function per cell:
- `_parse_date()` calls `pd.to_datetime(value, ...)` **per cell** — 1.5M calls
- `_parse_number()` does string manipulation per cell — 7.5M calls (5 numeric cols × 1.5M rows)
- `_normalise_categorical_column()` uses a Python `for` loop over `df[column].items()`
- `_normalise_daycount_column()` same pattern

**Fix**: Replace `.apply(lambda)` with vectorised pandas operations:
- Dates: `pd.to_datetime(df[col], dayfirst=True, errors="coerce")` (one call for entire column)
- Numbers: `df[col].str.replace(",", ".").astype(float)` (vectorised string ops)
- Categoricals: `df[col].str.strip().str.upper().map(mapping_dict)` (vectorised map)
- Daycount: same vectorised `.map()` pattern

### B3. Per-row serialization and canonicalization in main.py [HIGH]
**File**: `main.py:1367-1416`

Two Python `for` loops iterate over all motor records (~1.5M):

**Loop 1** (lines 1371-1375): `_serialize_value_for_json` called for every key-value pair:
```python
for rec in motor_records:           # 1.5M iterations
    for key, val in rec.items():    # ~20 keys each → 30M function calls
        rec[key] = _serialize_value_for_json(val)
```

**Loop 2** (lines 1389-1392): `_canonicalize_motor_row` called per record:
```python
for idx, rec in enumerate(motor_records):   # 1.5M iterations
    canonical_rows.append(_canonicalize_motor_row(rec, idx, ...))
```
Each call does ~15 function calls internally (`_to_text`, `_to_float`, `_to_iso_date`, `_bc_classify`, `_maturity_years`, `_bucket_from_years`).

**Fix**: Do both serialization and canonicalization as vectorised DataFrame operations BEFORE converting to dicts. Build the canonical DataFrame directly from the motor DataFrame using pandas column ops, then `.to_dict(orient="records")` once at the end.

### B4. JSON serialization of motor_positions.json [MEDIUM]
**File**: `main.py:1377-1380`

```python
json.dumps(motor_records, indent=2, ensure_ascii=False)
```

For 1.5M records × 20 keys, this produces a ~500MB+ JSON string with pretty-printing (`indent=2`). The `indent=2` parameter alone roughly doubles serialization time and output size.

**Fix**:
- Use `orjson` (10-50× faster than stdlib json) or at minimum drop `indent=2`
- Consider Parquet format instead of JSON for the motor positions (10-50× smaller, instant load via `pd.read_parquet`)

### B5. Synchronous blocking of FastAPI event loop [MEDIUM]
**File**: `main.py:1292` (the entire `_parse_zip_balance` function)

The function is synchronous and called from an `async` endpoint. While it runs (10+ minutes), the FastAPI event loop is completely blocked — no other requests can be served, including the progress polling endpoint.

**Fix**: Wrap in `asyncio.to_thread(_parse_zip_balance, ...)` so the event loop stays responsive. This is a one-line change at the call site.

### B6. Multiple DataFrame copies [LOW-MEDIUM]
**File**: `positions_reader.py:390,487,492,531`

The DataFrame is copied multiple times during processing:
```python
df = df.dropna(how="all").copy()    # copy 1
df = df.rename(columns=rename_map)   # copy 2 (rename returns new df)
df = df[keep_columns].copy()         # copy 3
```

For a 1.5M-row DataFrame with 80+ columns, each `.copy()` allocates ~1-2 GB.

**Fix**: Use `inplace=True` where possible, or chain operations to minimize intermediate copies. Drop unneeded columns early (before the heavy parsing) to reduce memory footprint.

---

## Implementation Plan (Ordered)

### Phase 1: Quick Wins (1 conversation, ~30 min)

#### 1.1 — Fix `_load_csv_table` double-read
In `positions_reader.py`, replace `path.read_text().splitlines()` with a partial read:

```python
def _load_csv_table(path, *, delimiter, encoding, header_token):
    # Only read first 50 lines to find header token
    for enc in _iter_csv_encodings(encoding):
        try:
            with open(path, encoding=enc) as f:
                head_lines = [next(f, None) for _ in range(50)]
                head_lines = [l for l in head_lines if l is not None]
        except UnicodeDecodeError:
            continue

        resolved_header_row = _find_header_row_from_lines(head_lines, header_token)
        if resolved_header_row is None:
            continue

        resolved_delimiter = delimiter or _detect_delimiter_from_line(head_lines[resolved_header_row])

        df = pd.read_csv(path, sep=resolved_delimiter, header=resolved_header_row,
                         encoding=enc, low_memory=False)
        return df.dropna(how="all"), resolved_header_row
```

**Impact**: Eliminates ~800 MB peak allocation for Non-maturity.csv. Halves I/O time.
**Bank-agnostic**: Yes — only changes HOW the header is found, not WHAT is looked for.

#### 1.2 — Wrap `_parse_zip_balance` in `asyncio.to_thread`
In `main.py`, the endpoint `upload_balance_zip` calls `_parse_zip_balance` synchronously:

```python
# Current:
sheet_summaries, sample_rows, canonical_rows = _parse_zip_balance(session_id, zip_path)

# Fixed:
import asyncio
sheet_summaries, sample_rows, canonical_rows = await asyncio.to_thread(
    _parse_zip_balance, session_id, zip_path
)
```

**Impact**: Event loop stays responsive. Progress polling works. No more `ERR_INSUFFICIENT_RESOURCES`.
**Bank-agnostic**: Yes — infrastructure change only.

#### 1.3 — Drop `indent=2` from motor JSON serialization
```python
# Current:
json.dumps(motor_records, indent=2, ensure_ascii=False)

# Fixed:
json.dumps(motor_records, ensure_ascii=False)
```
Or better, use `orjson` if available (add to requirements.txt):
```python
import orjson
path.write_bytes(orjson.dumps(motor_records))
```

**Impact**: 2-5× faster serialization, 30-50% smaller file.
**Bank-agnostic**: Yes.

### Phase 2: Vectorise Parsing (1 conversation, ~45 min)

#### 2.1 — Vectorise `_parse_date`
Replace per-cell `.apply(_parse_date)` with:
```python
for col in _DATE_COLUMNS:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], dayfirst=date_dayfirst, errors="coerce").dt.date
```

**Impact**: 10-50× faster for date columns.

#### 2.2 — Vectorise `_parse_number`
The current per-cell function handles comma/dot ambiguity. Vectorised version:
```python
for col in _NUMERIC_COLUMNS:
    if col in df.columns:
        s = df[col].astype(str).str.strip()
        s = s.str.replace("%", "", regex=False)
        s = s.str.replace(" ", "", regex=False)
        # Handle European decimal: "3,25" → "3.25"
        # If both , and . present, detect which is decimal
        has_both = s.str.contains(",", na=False) & s.str.contains(".", na=False)
        # For rows with both: use rfind logic or assume standard format
        # For rows with only comma: replace comma with dot
        s = s.where(has_both, s.str.replace(",", ".", regex=False))
        # ... handle has_both cases with .str.replace patterns
        df[col] = pd.to_numeric(s, errors="coerce")
```

**Impact**: 10-20× faster for 5 numeric columns.
**Note**: The comma/dot detection logic needs careful handling for bank-agnostic support. Keep the per-cell fallback for `has_both` edge cases if needed.

#### 2.3 — Vectorise `_normalise_categorical_column`
Replace Python for-loop with:
```python
def _normalise_categorical_column_vec(df, column, mapping, *, row_offset):
    map_norm = {str(k).strip().upper(): v for k, v in mapping.items()}
    canonical_norm = {str(v).strip().upper(): v for v in map_norm.values()}
    full_map = {**canonical_norm, **map_norm}

    normed = df[column].astype(str).str.strip().str.upper()
    result = normed.map(full_map)

    invalid = df[column].notna() & df[column].astype(str).str.strip().ne("") & result.isna()
    if invalid.any():
        # ... same error reporting
    return result
```

**Impact**: 5-10× faster.

#### 2.4 — Vectorise `_normalise_daycount_column`
Same pattern: build a lookup dict of known daycount strings → canonical values, use `.map()`.

### Phase 3: Vectorise Canonicalization (1 conversation, ~45 min)

#### 3.1 — Replace per-row `_canonicalize_motor_row` with DataFrame ops
Instead of iterating 1.5M records as Python dicts, build the canonical DataFrame directly:

```python
# Instead of:
canonical_rows = []
for idx, rec in enumerate(motor_records):
    canonical_rows.append(_canonicalize_motor_row(rec, idx))

# Do:
canonical_df = pd.DataFrame()
canonical_df["contract_id"] = motor_df["contract_id"].fillna(
    "motor-" + (motor_df.index + 1).astype(str)
)
canonical_df["sheet"] = motor_df["source_contract_type"].fillna("unknown")
# ... vectorised classification ...
canonical_df["amount"] = motor_df["notional"].fillna(0.0)
# ... etc for all fields ...
canonical_rows = canonical_df.to_dict(orient="records")
```

The `_bc_classify` call needs vectorisation too — build a lookup table from the classification rules and use `pd.merge` or `.map()` instead of per-row function calls.

**Impact**: 10-50× faster for the canonicalization phase.

#### 3.2 — Replace per-record `_serialize_value_for_json` with DataFrame-level conversion
Before calling `.to_dict()`, convert all columns to JSON-safe types at the DataFrame level:
```python
# Convert dates to ISO strings
for col in date_cols:
    motor_df[col] = motor_df[col].apply(lambda d: d.isoformat() if d else None)
# Convert numpy types to Python natives
motor_df = motor_df.astype(object).where(motor_df.notna(), None)
```

This eliminates 30M individual `_serialize_value_for_json` calls.

### Phase 4: Storage Format (Optional, 1 conversation, ~20 min)

#### 4.1 — Switch motor_positions from JSON to Parquet
```python
# Write:
motor_df.to_parquet(motor_positions_path, engine="pyarrow")

# Read (in /calculate):
motor_df = pd.read_parquet(motor_positions_path)
```

**Impact**:
- Write: ~1s vs ~60s (JSON)
- File size: ~50 MB vs ~500 MB
- Read (in /calculate): ~1s vs ~30s
- **Requires**: `pyarrow` in requirements.txt
- **Requires**: Update `/calculate` endpoint to read Parquet instead of JSON

---

## Expected Results

| Phase | Current (div4, 1.5M rows) | After | Speedup |
|-------|---------------------------|-------|---------|
| CSV loading | ~8 min | ~2 min | 4× |
| Parsing/canonicalization | ~5 min | ~30s | 10× |
| JSON serialization | ~2 min | ~5s (orjson) | 24× |
| Event loop blocking | 100% blocked | Responsive | ∞ |
| **Total** | **~15 min** | **~2.5 min** | **6×** |

With Phase 4 (Parquet): total drops to ~2 min.
For full bank data (4× scale): ~8-10 min instead of 60+ min.

---

## Constraints / Bank-Agnostic Notes

All optimizations are **bank-agnostic** — they don't depend on Unicaja's specific column structure:

1. **Header detection** (Phase 1.1): Still uses the configurable `header_token` from SOURCE_SPECS
2. **Vectorised parsing** (Phase 2): Operates on canonical column names (`start_date`, `notional`, etc.) that are the same for all banks after the mapping step
3. **Canonicalization** (Phase 3): Operates on the motor DataFrame which has the same schema regardless of source bank
4. **The bank mapping system** (`BANK_COLUMNS_MAP`, `SOURCE_SPECS`, etc.) is NOT modified — it continues to define how each bank's raw columns map to canonical names

The only bank-specific logic is in `bank_mapping_*.py` files, which are not touched by any of these optimizations.
