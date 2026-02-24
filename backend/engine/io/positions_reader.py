from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from engine.core.daycount import normalizar_base_de_calculo
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

    out: list[Any] = []
    for value in series:
        if pd.isna(value):
            out.append(pd.NA)
            continue

        token = str(value).strip()
        if token == "":
            out.append(pd.NA)
            continue

        if token in exact:
            out.append(exact[token])
            continue

        folded_key = _norm_token(token)
        if folded_key in folded:
            out.append(folded[folded_key])
            continue

        out.append(token)

    return pd.Series(out, index=series.index, dtype="object")



def _normalise_categorical_column(
    df: pd.DataFrame,
    column: str,
    mapping: Mapping[str, str],
    *,
    row_offset: int,
) -> pd.Series:
    map_norm = {_norm_token(k): v for k, v in mapping.items()}
    canonical_norm = {_norm_token(v): v for v in map_norm.values()}

    out: list[Any] = []
    invalid_rows: list[int] = []
    invalid_values: list[Any] = []

    for idx, value in df[column].items():
        if pd.isna(value) or str(value).strip() == "":
            out.append(None)
            continue

        token = _norm_token(value)
        if token in map_norm:
            out.append(map_norm[token])
            continue
        if token in canonical_norm:
            out.append(canonical_norm[token])
            continue

        out.append(None)
        invalid_rows.append(int(idx) + row_offset)
        invalid_values.append(value)

    if invalid_rows:
        values = sorted({str(v) for v in invalid_values})
        rows = invalid_rows[:10]
        raise ValueError(
            f"Valores no reconocidos en '{column}' para filas {rows}: {values}"
        )

    return pd.Series(out, index=df.index, dtype="object")


def _normalise_daycount_column(
    df: pd.DataFrame,
    column: str,
    *,
    row_offset: int,
) -> pd.Series:
    out: list[Any] = []
    invalid_rows: list[int] = []
    invalid_values: list[Any] = []

    for idx, value in df[column].items():
        if pd.isna(value) or str(value).strip() == "":
            out.append(None)
            continue
        try:
            out.append(normalizar_base_de_calculo(str(value)))
        except Exception:
            out.append(None)
            invalid_rows.append(int(idx) + row_offset)
            invalid_values.append(value)

    if invalid_rows:
        values = sorted({str(v) for v in invalid_values})
        rows = invalid_rows[:10]
        raise ValueError(
            f"Bases de calculo no reconocidas en '{column}' para filas {rows}: {values}"
        )

    return pd.Series(out, index=df.index, dtype="object")


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
        f"No se pudo parsear {kind} en columna '{column}' para filas {rows}: {values}"
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
        missing = df[col].apply(_is_blank_cell)
        if missing.any():
            rows = [int(i) + row_offset for i in df.index[missing][:10].tolist()]
            raise ValueError(f"Columna requerida '{col}' vacia en filas {rows}")


def _build_rename_map(
    source_columns: list[str],
    bank_columns_map: Mapping[str, str],
) -> dict[str, str]:
    norm_to_source: dict[str, str] = {}
    for col in source_columns:
        key = _norm_header(col)
        if key in norm_to_source and norm_to_source[key] != col:
            raise ValueError(
                f"Cabeceras ambiguas tras normalizacion: '{norm_to_source[key]}' y '{col}'"
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
                f"Dos columnas origen mapean a '{canonical_col}': '{prev}' y '{source_col}'"
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
    ordered: list[str] = []
    if preferred_encoding:
        ordered.append(preferred_encoding)
    ordered.extend(_DEFAULT_CSV_ENCODINGS)

    dedup: list[str] = []
    seen: set[str] = set()
    for enc in ordered:
        key = enc.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(enc)
    return dedup


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


def _load_csv_table(
    path: Path,
    *,
    delimiter: str | None,
    encoding: str | None,
    header_row: int | None,
    header_token: str | None,
) -> tuple[pd.DataFrame, int]:
    if header_row is None and not header_token:
        raise ValueError("Para CSV debes indicar header_row o header_token.")

    last_error: Exception | None = None

    for enc in _iter_csv_encodings(encoding):
        try:
            lines = path.read_text(encoding=enc).splitlines()
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        resolved_header_row = 0 if header_row is None else int(header_row)
        if header_token:
            found = _find_header_row_from_lines(lines, header_token)
            if found is None:
                last_error = ValueError(
                    f"No se encontro header_token='{header_token}' en {path}"
                )
                continue
            resolved_header_row = found

        if not lines:
            return pd.DataFrame(), resolved_header_row

        if resolved_header_row < 0 or resolved_header_row >= len(lines):
            last_error = ValueError(
                f"header_row fuera de rango ({resolved_header_row}) en {path}"
            )
            continue

        resolved_delimiter = delimiter or _detect_delimiter_from_line(lines[resolved_header_row])
        try:
            df = pd.read_csv(
                path,
                sep=resolved_delimiter,
                header=resolved_header_row,
                encoding=enc,
            )
        except Exception as exc:
            last_error = exc
            continue

        df = df.dropna(how="all").copy()
        return df, resolved_header_row

    if last_error is not None:
        raise ValueError(f"No se pudo leer CSV '{path}': {last_error}") from last_error
    raise ValueError(f"No se pudo leer CSV '{path}'.")


def _resolve_row_kind_column_name(
    df: pd.DataFrame,
    row_kind_column: str | int | None,
) -> str | None:
    if row_kind_column is None:
        return None

    if isinstance(row_kind_column, int):
        if row_kind_column < 0 or row_kind_column >= len(df.columns):
            raise ValueError(f"row_kind_column index fuera de rango: {row_kind_column}")
        return str(df.columns[row_kind_column])

    if row_kind_column not in df.columns:
        raise ValueError(f"row_kind_column no existe en datos: {row_kind_column}")
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
        raise ValueError("include_row_kinds requiere row_kind_column.")

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
        raise ValueError("NUMERIC_SCALE_MAP debe ser Mapping[columna, factor].")
    if not isinstance(default_values_raw, Mapping):
        raise ValueError("DEFAULT_CANONICAL_VALUES debe ser Mapping[columna, valor].")
    if not isinstance(index_aliases_raw, Mapping):
        raise ValueError("INDEX_NAME_ALIASES debe ser Mapping[origen, destino].")

    numeric_scale_map = {str(k): float(v) for k, v in numeric_scale_map_raw.items()}
    default_values = {str(k): v for k, v in default_values_raw.items()}
    index_aliases = {str(k): str(v) for k, v in index_aliases_raw.items()}
    if canonical_defaults_override is not None:
        default_values.update({str(k): v for k, v in canonical_defaults_override.items()})

    df = df.dropna(how="all").copy()
    if df.empty:
        raise ValueError("Fichero de posiciones vacio o sin filas validas.")

    rename_map = _build_rename_map(df.columns.tolist(), bank_columns_map)
    df = df.rename(columns=rename_map)

    missing_required = [c for c in required_columns if c not in df.columns and c not in default_values]
    if missing_required:
        reverse_map: dict[str, list[str]] = {}
        for source_col, canonical_col in bank_columns_map.items():
            reverse_map.setdefault(canonical_col, []).append(source_col)

        details = {
            col: reverse_map.get(col, ["<sin mapping definido>"])
            for col in missing_required
        }
        raise ValueError(
            "Faltan columnas canonicas requeridas tras mapping: "
            f"{missing_required}. Esperadas en origen: {details}"
        )

    canonical_order = list(dict.fromkeys(required_columns + optional_columns))
    for col in optional_columns:
        if col not in df.columns:
            df[col] = pd.NA

    for col, value in default_values.items():
        if col not in df.columns:
            df[col] = value
            continue
        missing_mask = df[col].apply(_is_blank_cell)
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
        parsed = df[col].apply(lambda x: _parse_date(x, dayfirst=date_dayfirst))
        _error_if_invalid_parse(df, col, parsed, "fecha", row_offset=row_offset)
        df[col] = parsed

    for col in _NUMERIC_COLUMNS:
        if col not in df.columns:
            continue
        parsed = df[col].apply(
            lambda x: _parse_number(x, allow_percent=(col in _PERCENT_COLUMNS))
        )
        _error_if_invalid_parse(df, col, parsed, "numero", row_offset=row_offset)
        scale = float(numeric_scale_map.get(col, 1.0))
        if scale != 1.0:
            parsed = parsed.apply(lambda x: None if pd.isna(x) else float(x) * scale)
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
        missing_index = float_rows & df["index_name"].apply(_is_blank_cell)
        if missing_index.any():
            rows = [int(i) + row_offset for i in df.index[missing_index][:10].tolist()]
            raise ValueError(
                "Posiciones float sin index_name (proyeccion) en filas "
                f"{rows}"
            )

    if "rate_type" in df.columns and "fixed_rate" in df.columns:
        fixed_rows = df["rate_type"] == "fixed"
        missing_fixed_rate = fixed_rows & df["fixed_rate"].apply(_is_blank_cell)
        if missing_fixed_rate.any():
            rows = [int(i) + row_offset for i in df.index[missing_fixed_rate][:10].tolist()]
            raise ValueError(f"Posiciones fixed sin fixed_rate en filas {rows}")

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
) -> tuple[pd.DataFrame, int]:
    """
    Lee un CSV/Excel en bruto (sin mapping), devolviendo:
    - DataFrame con filas no vacias
    - indice de fila de cabecera detectado/usado
    """

    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"No existe el fichero de posiciones: {input_path}")

    resolved_type = file_type.lower()
    if resolved_type == "auto":
        suffix = input_path.suffix.lower()
        if suffix in {".xls", ".xlsx", ".xlsm"}:
            resolved_type = "excel"
        elif suffix == ".csv":
            resolved_type = "csv"
        else:
            raise ValueError(f"Extension no soportada para posiciones: {input_path.suffix}")

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
        )
    else:
        raise ValueError(f"file_type no soportado: {file_type}")

    return df_raw.dropna(how="all").copy(), resolved_header_row


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
