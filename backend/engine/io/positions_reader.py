from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from engine.core.daycount import DAYCOUNT_BASE_MAP, normalize_daycount_base
from engine.io._utils import (
    mapping_attr as _mapping_attr,
    mapping_attr_optional as _mapping_attr_optional,
    norm_header as _norm_header,
    parse_date as _parse_date,
    parse_number as _parse_number,
)


_PERCENT_COLUMNS = {"spread", "fixed_rate", "floor_rate", "cap_rate"}
_NUMERIC_COLUMNS = {"notional", *_PERCENT_COLUMNS}
_DATE_COLUMNS = {"start_date", "maturity_date", "next_reprice_date"}

_DEFAULT_CSV_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
_DEFAULT_CSV_DELIMITERS = (",", ";", "\t", "|")


def _norm_token(value: Any) -> str:
    """Upper-case token normaliser (always returns str, never None)."""
    return str(value).strip().upper()


def _slugify_column_name(value: Any) -> str:
    s = str(value).strip().lower()
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")
    return s or "column"


def _apply_text_aliases(
    series: pd.Series,
    aliases: Mapping[str, str],
) -> pd.Series:
    if not aliases:
        return series

    exact = {str(k).strip(): str(v).strip() for k, v in aliases.items()}
    folded = {_norm_token(k): str(v).strip() for k, v in aliases.items()}

    stripped = series.astype(str).str.strip()
    blank_mask = series.isna() | stripped.eq("")

    # Try exact match, then case-insensitive (folded) match
    exact_mapped = stripped.map(exact)
    folded_mapped = stripped.str.upper().map(folded)

    # Priority: exact > folded > original
    result = exact_mapped.where(exact_mapped.notna(), folded_mapped)
    result = result.where(result.notna(), stripped)
    result = result.where(~blank_mask, other=pd.NA)

    return pd.Series(result.values, index=series.index, dtype="object")



def _normalise_categorical_column(
    df: pd.DataFrame,
    column: str,
    mapping: Mapping[str, str],
    *,
    row_offset: int,
) -> pd.Series:
    map_norm = {_norm_token(k): v for k, v in mapping.items()}
    canonical_norm = {_norm_token(v): v for v in map_norm.values()}
    # Merged lookup: canonical takes precedence, then bank tokens
    full_map = {**canonical_norm, **map_norm}

    raw = df[column]
    blank_mask = raw.isna() | raw.astype(str).str.strip().eq("")
    normed = raw.astype(str).str.strip().str.upper()
    result = normed.map(full_map)
    result = result.where(~blank_mask, other=None)

    invalid = ~blank_mask & result.isna()
    if invalid.any():
        rows = [int(i) + row_offset for i in raw[invalid].index[:10].tolist()]
        values = sorted({str(v) for v in raw[invalid].head(10).tolist()})
        raise ValueError(
            f"Unrecognized values in '{column}' for rows {rows}: {values}"
        )

    return result


def _normalise_daycount_column(
    df: pd.DataFrame,
    column: str,
    *,
    row_offset: int,
) -> pd.Series:
    raw = df[column]
    blank_mask = raw.isna() | raw.astype(str).str.strip().eq("")

    # Replicate the normalize_daycount_base() string normalization vectorised
    normed = raw.astype(str).str.strip().str.upper()
    normed = normed.str.replace(" ", "", regex=False).str.replace("-", "/", regex=False)
    for ch in ("(", ")", "[", "]"):
        normed = normed.str.replace(ch, "", regex=False)
    normed = normed.str.replace("30/360E", "30E/360", regex=False)
    normed = normed.str.replace("US", "", regex=False)
    normed = normed.str.replace("NASD", "", regex=False)
    normed = normed.str.replace("FIXED", "F", regex=False)

    result = normed.map(DAYCOUNT_BASE_MAP)
    result = result.where(~blank_mask, other=None)

    invalid = ~blank_mask & result.isna()
    if invalid.any():
        rows = [int(i) + row_offset for i in raw[invalid].index[:10].tolist()]
        values = sorted({str(v) for v in raw[invalid].head(10).tolist()})
        raise ValueError(
            f"Unrecognized daycount bases in '{column}' for rows {rows}: {values}"
        )

    return result


def _parse_numeric_column(series: pd.Series, *, allow_percent: bool) -> pd.Series:
    """Vectorised numeric parser handling comma/dot ambiguity and percent signs."""
    s = series.astype(str).str.strip()

    # Detect percent signs before stripping them
    has_pct = s.str.contains("%", na=False)
    s = s.str.replace("%", "", regex=False).str.replace(" ", "", regex=False)

    # Blank / NaN sentinels
    s = s.replace({"nan": "", "None": "", "none": "", "<NA>": "", "NaN": "", "NaT": ""})

    # Comma/dot ambiguity
    has_comma = s.str.contains(",", na=False)
    has_dot = s.str.contains(".", na=False, regex=False)
    has_both = has_comma & has_dot
    comma_last = s.str.rfind(",") > s.str.rfind(".")

    # European: 1.000,50 → 1000.50 (both present, comma after dot)
    euro = has_both & comma_last
    s = s.where(~euro, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    # US: 1,000.50 → 1000.50 (both present, dot after comma)
    us = has_both & ~comma_last
    s = s.where(~us, s.str.replace(",", "", regex=False))
    # Only comma: 3,25 → 3.25
    only_comma = has_comma & ~has_dot
    s = s.where(~only_comma, s.str.replace(",", ".", regex=False))

    s = s.replace({"": pd.NA})
    parsed = pd.to_numeric(s, errors="coerce")

    # Apply percent division for values that had %
    if allow_percent and has_pct.any():
        parsed = parsed.where(~has_pct, parsed / 100.0)

    return parsed


def _error_if_invalid_parse(
    df: pd.DataFrame,
    column: str,
    parsed: pd.Series,
    kind: str,
    *,
    row_offset: int,
) -> None:
    raw = df[column]
    invalid = raw.notna() & parsed.isna() & raw.astype(str).str.strip().ne("")
    if not invalid.any():
        return

    rows = [int(i) + row_offset for i in raw[invalid].index[:10].tolist()]
    values = sorted({str(v) for v in raw[invalid].head(10).tolist()})
    raise ValueError(
        f"Could not parse {kind} in column '{column}' for rows {rows}: {values}"
    )


def _is_blank_cell(value: Any) -> bool:
    if pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _check_required_not_null(
    df: pd.DataFrame,
    required_columns: list[str],
    *,
    row_offset: int,
) -> None:
    for col in required_columns:
        missing = df[col].isna() | df[col].astype(str).str.strip().eq("")
        if missing.any():
            rows = [int(i) + row_offset for i in df.index[missing][:10].tolist()]
            raise ValueError(f"Required column '{col}' empty in rows {rows}")


def _build_rename_map(
    source_columns: list[str],
    bank_columns_map: Mapping[str, str],
) -> dict[str, str]:
    norm_to_source: dict[str, str] = {}
    for col in source_columns:
        key = _norm_header(col)
        if key in norm_to_source and norm_to_source[key] != col:
            raise ValueError(
                f"Ambiguous headers after normalization: '{norm_to_source[key]}' and '{col}'"
            )
        norm_to_source[key] = col

    rename: dict[str, str] = {}
    seen_canonical: dict[str, str] = {}

    for bank_col, canonical_col in bank_columns_map.items():
        lookup_key = _norm_header(bank_col)
        if lookup_key not in norm_to_source:
            continue

        source_col = norm_to_source[lookup_key]
        if canonical_col in seen_canonical and seen_canonical[canonical_col] != source_col:
            prev = seen_canonical[canonical_col]
            raise ValueError(
                f"Two source columns map to '{canonical_col}': '{prev}' and '{source_col}'"
            )

        rename[source_col] = canonical_col
        seen_canonical[canonical_col] = source_col

    return rename


def _build_unmapped_rename(
    source_columns: list[str],
    canonical_columns: list[str],
    prefix: str,
) -> dict[str, str]:
    used = set(canonical_columns)
    rename: dict[str, str] = {}

    for col in source_columns:
        if col in used:
            continue

        base = f"{prefix}{_slugify_column_name(col)}"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used.add(candidate)
        rename[col] = candidate

    return rename


def _iter_csv_encodings(preferred_encoding: str | None) -> list[str]:
    # When the spec explicitly declares an encoding, trust it and skip fallbacks.
    # This avoids 2-3 failed decode attempts per file (e.g., trying utf-8 before cp1252).
    if preferred_encoding:
        return [preferred_encoding]

    return list(_DEFAULT_CSV_ENCODINGS)


def _detect_delimiter_from_line(line: str) -> str:
    best = ","
    best_count = -1
    for delim in _DEFAULT_CSV_DELIMITERS:
        count = line.count(delim)
        if count > best_count:
            best = delim
            best_count = count
    return best


def _find_header_row_from_lines(lines: list[str], header_token: str) -> int | None:
    token = _norm_header(header_token)
    for idx, line in enumerate(lines):
        if token in _norm_header(line):
            return idx
    return None


_HEADER_SEARCH_LINES = 50


def _load_csv_table(
    path: Path,
    *,
    delimiter: str | None,
    encoding: str | None,
    header_row: int | None,
    header_token: str | None,
    on_rows_read: Callable[[int], None] | None = None,
) -> tuple[pd.DataFrame, int]:
    if header_row is None and not header_token:
        raise ValueError("For CSV you must specify header_row or header_token.")

    last_error: Exception | None = None

    for enc in _iter_csv_encodings(encoding):
        # Only read first N lines to find the header — avoids loading
        # the entire file (potentially hundreds of MB) into a Python string.
        try:
            with open(path, encoding=enc) as fh:
                head_lines: list[str] = []
                for _ in range(_HEADER_SEARCH_LINES):
                    line = fh.readline()
                    if not line:
                        break
                    head_lines.append(line.rstrip("\n\r"))
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        resolved_header_row = 0 if header_row is None else int(header_row)
        if header_token:
            found = _find_header_row_from_lines(head_lines, header_token)
            if found is None:
                last_error = ValueError(
                    f"Could not find header_token='{header_token}' in {path}"
                )
                continue
            resolved_header_row = found

        if not head_lines:
            return pd.DataFrame(), resolved_header_row

        if resolved_header_row < 0 or resolved_header_row >= len(head_lines):
            last_error = ValueError(
                f"header_row out of range ({resolved_header_row}) in {path}"
            )
            continue

        resolved_delimiter = delimiter or _detect_delimiter_from_line(head_lines[resolved_header_row])
        try:
            if on_rows_read is not None:
                reader = pd.read_csv(
                    path,
                    sep=resolved_delimiter,
                    header=resolved_header_row,
                    encoding=enc,
                    chunksize=200_000,
                )
                chunks: list[pd.DataFrame] = []
                cumulative = 0
                for chunk in reader:
                    chunks.append(chunk)
                    cumulative += len(chunk)
                    on_rows_read(cumulative)
                df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            else:
                df = pd.read_csv(
                    path,
                    sep=resolved_delimiter,
                    header=resolved_header_row,
                    encoding=enc,
                    low_memory=False,
                )
        except Exception as exc:
            last_error = exc
            continue

        df = df.dropna(how="all")
        return df, resolved_header_row

    if last_error is not None:
        raise ValueError(f"Could not read CSV '{path}': {last_error}") from last_error
    raise ValueError(f"Could not read CSV '{path}'.")


def _resolve_row_kind_column_name(
    df: pd.DataFrame,
    row_kind_column: str | int | None,
) -> str | None:
    if row_kind_column is None:
        return None

    if isinstance(row_kind_column, int):
        if row_kind_column < 0 or row_kind_column >= len(df.columns):
            raise ValueError(f"row_kind_column index out of range: {row_kind_column}")
        return str(df.columns[row_kind_column])

    if row_kind_column not in df.columns:
        raise ValueError(f"row_kind_column does not exist in data: {row_kind_column}")
    return row_kind_column


def _apply_row_kind_filter(
    df: pd.DataFrame,
    *,
    row_kind_column: str | int | None,
    include_row_kinds: Iterable[str] | None,
    drop_row_kind_column: bool,
) -> pd.DataFrame:
    if include_row_kinds is None:
        return df

    col_name = _resolve_row_kind_column_name(df, row_kind_column)
    if col_name is None:
        raise ValueError("include_row_kinds requires row_kind_column.")

    allowed = {str(v).strip().lower() for v in include_row_kinds}
    tags = df[col_name].astype(str).str.strip().str.lower()
    filtered = df.loc[tags.isin(allowed)].copy()

    if drop_row_kind_column and col_name in filtered.columns:
        filtered = filtered.drop(columns=[col_name])

    return filtered


def read_positions_dataframe(
    df: pd.DataFrame,
    mapping_module: Any,
    *,
    row_offset: int = 2,
    canonical_defaults_override: Mapping[str, Any] | None = None,
    reset_index: bool = True,
) -> pd.DataFrame:
    """
    Applies bank -> canonical mapping over an already loaded DataFrame.

    Optional mapping_module attributes:
    - DATE_DAYFIRST: bool (default True)
    - NUMERIC_SCALE_MAP: dict[canonical_column, scale_factor]
    - DEFAULT_CANONICAL_VALUES: dict[canonical_column, value]
    - INDEX_NAME_ALIASES: dict[source_index_name, canonical_index_name]
    - PRESERVE_UNMAPPED_COLUMNS: bool (default False)
    - UNMAPPED_PREFIX: str (default "extra_")
    """

    required_columns = list(_mapping_attr(mapping_module, "REQUIRED_CANONICAL_COLUMNS"))
    optional_columns = list(_mapping_attr(mapping_module, "OPTIONAL_CANONICAL_COLUMNS"))
    bank_columns_map = _mapping_attr(mapping_module, "BANK_COLUMNS_MAP")
    side_map = _mapping_attr(mapping_module, "SIDE_MAP")
    rate_type_map = _mapping_attr(mapping_module, "RATE_TYPE_MAP")

    date_dayfirst = bool(_mapping_attr_optional(mapping_module, "DATE_DAYFIRST", True))
    numeric_scale_map_raw = _mapping_attr_optional(mapping_module, "NUMERIC_SCALE_MAP", {})
    default_values_raw = _mapping_attr_optional(mapping_module, "DEFAULT_CANONICAL_VALUES", {})
    preserve_unmapped = bool(
        _mapping_attr_optional(mapping_module, "PRESERVE_UNMAPPED_COLUMNS", False)
    )
    unmapped_prefix = str(_mapping_attr_optional(mapping_module, "UNMAPPED_PREFIX", "extra_"))
    index_aliases_raw = _mapping_attr_optional(mapping_module, "INDEX_NAME_ALIASES", {})

    if not isinstance(numeric_scale_map_raw, Mapping):
        raise ValueError("NUMERIC_SCALE_MAP must be a Mapping[column, factor].")
    if not isinstance(default_values_raw, Mapping):
        raise ValueError("DEFAULT_CANONICAL_VALUES must be a Mapping[column, value].")
    if not isinstance(index_aliases_raw, Mapping):
        raise ValueError("INDEX_NAME_ALIASES must be a Mapping[source, target].")

    numeric_scale_map = {str(k): float(v) for k, v in numeric_scale_map_raw.items()}
    default_values = {str(k): v for k, v in default_values_raw.items()}
    index_aliases = {str(k): str(v) for k, v in index_aliases_raw.items()}
    if canonical_defaults_override is not None:
        default_values.update({str(k): v for k, v in canonical_defaults_override.items()})

    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("Positions file is empty or has no valid rows.")

    rename_map = _build_rename_map(df.columns.tolist(), bank_columns_map)
    df.rename(columns=rename_map, inplace=True)

    missing_required = [c for c in required_columns if c not in df.columns and c not in default_values]
    if missing_required:
        reverse_map: dict[str, list[str]] = {}
        for source_col, canonical_col in bank_columns_map.items():
            reverse_map.setdefault(canonical_col, []).append(source_col)

        details = {
            col: reverse_map.get(col, ["<no mapping defined>"])
            for col in missing_required
        }
        raise ValueError(
            "Missing required canonical columns after mapping: "
            f"{missing_required}. Expected in source: {details}"
        )

    canonical_order = list(dict.fromkeys(required_columns + optional_columns))
    for col in optional_columns:
        if col not in df.columns:
            df[col] = pd.NA

    for col, value in default_values.items():
        if col not in df.columns:
            df[col] = value
            continue
        missing_mask = df[col].isna() | df[col].astype(str).str.strip().eq("")
        if missing_mask.any():
            df.loc[missing_mask, col] = value

    extra_columns = [c for c in df.columns if c not in canonical_order]
    extra_keep: list[str] = []
    if preserve_unmapped and extra_columns:
        extra_rename = _build_unmapped_rename(extra_columns, canonical_order, unmapped_prefix)
        df = df.rename(columns=extra_rename)
        extra_keep = [extra_rename[c] for c in extra_columns]

    keep_columns = [c for c in canonical_order if c in df.columns]
    keep_columns.extend(extra_keep)
    df = df[keep_columns].copy()

    for col in _DATE_COLUMNS:
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], dayfirst=date_dayfirst, errors="coerce")
        _error_if_invalid_parse(df, col, parsed, "date", row_offset=row_offset)
        df[col] = parsed

    for col in _NUMERIC_COLUMNS:
        if col not in df.columns:
            continue
        parsed = _parse_numeric_column(df[col], allow_percent=(col in _PERCENT_COLUMNS))
        _error_if_invalid_parse(df, col, parsed, "number", row_offset=row_offset)
        scale = float(numeric_scale_map.get(col, 1.0))
        if scale != 1.0:
            parsed = parsed * scale
        df[col] = parsed

    if "spread" in df.columns:
        df["spread"] = df["spread"].fillna(0.0)

    if "contract_id" in df.columns:
        df["contract_id"] = df["contract_id"].astype("string").str.strip()

    if "index_name" in df.columns:
        df["index_name"] = df["index_name"].astype("string").str.strip()
        df["index_name"] = df["index_name"].replace({"": pd.NA})
        if index_aliases:
            df["index_name"] = _apply_text_aliases(df["index_name"], index_aliases)
            df["index_name"] = df["index_name"].replace({"": pd.NA})

    if "side" in df.columns:
        df["side"] = _normalise_categorical_column(
            df,
            "side",
            side_map,
            row_offset=row_offset,
        )

    if "rate_type" in df.columns:
        df["rate_type"] = _normalise_categorical_column(
            df,
            "rate_type",
            rate_type_map,
            row_offset=row_offset,
        )

    if "daycount_base" in df.columns:
        df["daycount_base"] = _normalise_daycount_column(
            df,
            "daycount_base",
            row_offset=row_offset,
        )

    _check_required_not_null(df, required_columns, row_offset=row_offset)

    if "start_date" in df.columns and "maturity_date" in df.columns:
        valid_dates = df["start_date"].notna() & df["maturity_date"].notna()
        bad_dates = valid_dates & (df["start_date"] > df["maturity_date"])
        if bad_dates.any():
            rows = [int(i) + row_offset for i in df.index[bad_dates][:10].tolist()]
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Dropping %d rows with start_date > maturity_date (e.g. rows %s)",
                int(bad_dates.sum()), rows,
            )
            df.drop(df.index[bad_dates], inplace=True)

    if "rate_type" in df.columns and "index_name" in df.columns:
        float_rows = df["rate_type"] == "float"
        missing_index = float_rows & (df["index_name"].isna() | df["index_name"].astype(str).str.strip().eq(""))
        if missing_index.any():
            rows = [int(i) + row_offset for i in df.index[missing_index][:10].tolist()]
            raise ValueError(
                "Float positions without index_name (projection) in rows "
                f"{rows}"
            )

    if "rate_type" in df.columns and "fixed_rate" in df.columns:
        fixed_rows = df["rate_type"] == "fixed"
        missing_fixed_rate = fixed_rows & df["fixed_rate"].isna()
        if missing_fixed_rate.any():
            rows = [int(i) + row_offset for i in df.index[missing_fixed_rate][:10].tolist()]
            raise ValueError(f"Fixed positions without fixed_rate in rows {rows}")

    if reset_index:
        return df.reset_index(drop=True)
    return df


def read_positions_tabular(
    path: str | Path,
    mapping_module: Any,
    *,
    file_type: str = "auto",
    sheet_name: str | int = 0,
    delimiter: str | None = None,
    encoding: str | None = None,
    header_row: int | None = 0,
    header_token: str | None = None,
    row_kind_column: str | int | None = None,
    include_row_kinds: Iterable[str] | None = None,
    drop_row_kind_column: bool = True,
    canonical_defaults_override: Mapping[str, Any] | None = None,
    source_row_column: str | None = None,
    reset_index: bool = True,
    on_rows_read: Callable[[int], None] | None = None,
) -> pd.DataFrame:
    """
    Reads a tabular file (CSV/Excel), optionally filters row kinds, and maps it.

    Typical cases:
    - CSV with metadata and real header lower in file: header_token="Identifier"
    - CSV with mixed rows contract/payment: row_kind_column=0 and include_row_kinds=["contract"]
    """

    df_raw, resolved_header_row = read_tabular_raw(
        path=path,
        file_type=file_type,
        sheet_name=sheet_name,
        delimiter=delimiter,
        encoding=encoding,
        header_row=header_row,
        header_token=header_token,
        on_rows_read=on_rows_read,
    )
    df_raw = _apply_row_kind_filter(
        df_raw,
        row_kind_column=row_kind_column,
        include_row_kinds=include_row_kinds,
        drop_row_kind_column=drop_row_kind_column,
    )

    row_offset = resolved_header_row + 2
    out = read_positions_dataframe(
        df_raw,
        mapping_module,
        row_offset=row_offset,
        canonical_defaults_override=canonical_defaults_override,
        reset_index=False,
    )

    if source_row_column:
        out[source_row_column] = out.index.to_series().astype("int64") + row_offset

    if reset_index:
        return out.reset_index(drop=True)
    return out


def read_tabular_raw(
    path: str | Path,
    *,
    file_type: str = "auto",
    sheet_name: str | int = 0,
    delimiter: str | None = None,
    encoding: str | None = None,
    header_row: int | None = 0,
    header_token: str | None = None,
    on_rows_read: Callable[[int], None] | None = None,
) -> tuple[pd.DataFrame, int]:
    """
    Reads a CSV/Excel file in raw form (without mapping), returning:
    - DataFrame with non-empty rows
    - detected/used header row index
    """

    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Positions file does not exist: {input_path}")

    resolved_type = file_type.lower()
    if resolved_type == "auto":
        suffix = input_path.suffix.lower()
        if suffix in {".xls", ".xlsx", ".xlsm"}:
            resolved_type = "excel"
        elif suffix == ".csv":
            resolved_type = "csv"
        else:
            raise ValueError(f"Unsupported extension for positions: {input_path.suffix}")

    if resolved_type == "excel":
        resolved_header_row = 0 if header_row is None else int(header_row)
        df_raw = pd.read_excel(
            input_path,
            sheet_name=sheet_name,
            header=resolved_header_row,
            engine="openpyxl",
        )
    elif resolved_type == "csv":
        df_raw, resolved_header_row = _load_csv_table(
            input_path,
            delimiter=delimiter,
            encoding=encoding,
            header_row=header_row,
            header_token=header_token,
            on_rows_read=on_rows_read,
        )
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")

    return df_raw.dropna(how="all"), resolved_header_row


def read_positions_excel(
    path: str | Path,
    mapping_module: Any,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    """
    Backward-compatible wrapper: Excel -> canonical mapping.
    """

    return read_positions_tabular(
        path=path,
        mapping_module=mapping_module,
        file_type="excel",
        sheet_name=sheet_name,
        header_row=0,
        reset_index=True,
    )
