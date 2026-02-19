from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from almready.io.positions_reader import read_positions_tabular


def _mapping_attr(mapping_module: Any, attr_name: str) -> Any:
    if isinstance(mapping_module, Mapping):
        if attr_name not in mapping_module:
            raise ValueError(f"mapping_module sin clave requerida: {attr_name}")
        return mapping_module[attr_name]

    if not hasattr(mapping_module, attr_name):
        raise ValueError(f"mapping_module sin atributo requerido: {attr_name}")
    return getattr(mapping_module, attr_name)


def _to_sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _resolve_glob_matches(root_path: Path, pattern: str) -> list[Path]:
    return sorted(p for p in root_path.glob(pattern) if p.is_file())


def load_positions_from_specs(
    root_path: str | Path,
    mapping_module: Any,
    *,
    source_specs: Sequence[Mapping[str, Any]] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """
    Loads and canonicalises positions from multiple files using declarative SOURCE_SPECS.

    Expected SOURCE_SPECS entry keys:
    - name: str (optional)
    - pattern: str (required, glob relative to root_path)
    - file_type/kind: "auto" | "csv" | "excel" (optional, default "auto")
    - sheet_name: str|int (optional)
    - sheet_names: list[str|int] (optional, takes precedence over sheet_name)
    - delimiter, encoding, header_row, header_token (optional)
    - row_kind_column, include_row_kinds, drop_row_kind_column (optional)
    - defaults: dict[canonical_column, value] (optional)
    - source_bank, source_contract_type (optional)
    - required: bool (optional, default True)
    """

    base_path = Path(root_path)
    if not base_path.exists():
        raise FileNotFoundError(f"No existe root_path para posiciones: {base_path}")

    specs = (
        list(source_specs)
        if source_specs is not None
        else list(_mapping_attr(mapping_module, "SOURCE_SPECS"))
    )
    if not specs:
        raise ValueError("SOURCE_SPECS vacio: define al menos una fuente.")

    frames: list[pd.DataFrame] = []
    total_specs = len(specs)

    for idx, raw_spec in enumerate(specs, start=1):
        if not isinstance(raw_spec, Mapping):
            raise ValueError(f"SOURCE_SPECS[{idx}] debe ser Mapping, recibido: {type(raw_spec)}")

        pattern = raw_spec.get("pattern")
        if not pattern:
            raise ValueError(f"SOURCE_SPECS[{idx}] sin 'pattern'.")

        spec_name = str(raw_spec.get("name", pattern))
        file_type = str(raw_spec.get("file_type", raw_spec.get("kind", "auto")))
        required = bool(raw_spec.get("required", True))
        sheet_names = raw_spec.get("sheet_names", raw_spec.get("sheet_name", 0))
        defaults = raw_spec.get("defaults")

        matches = _resolve_glob_matches(base_path, str(pattern))
        if not matches:
            if required:
                raise FileNotFoundError(
                    f"No se encontro ningun fichero para pattern='{pattern}' en {base_path}"
                )
            continue

        for source_file in matches:
            if file_type.lower() == "csv":
                effective_sheets = [0]
            else:
                effective_sheets = _to_sequence(sheet_names)

            for sheet in effective_sheets:
                df = read_positions_tabular(
                    path=source_file,
                    mapping_module=mapping_module,
                    file_type=file_type,
                    sheet_name=sheet,
                    delimiter=raw_spec.get("delimiter"),
                    encoding=raw_spec.get("encoding"),
                    header_row=raw_spec.get("header_row", 0),
                    header_token=raw_spec.get("header_token"),
                    row_kind_column=raw_spec.get("row_kind_column"),
                    include_row_kinds=raw_spec.get("include_row_kinds"),
                    drop_row_kind_column=bool(raw_spec.get("drop_row_kind_column", True)),
                    canonical_defaults_override=defaults,
                    source_row_column="source_row",
                    reset_index=True,
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

                frames.append(df)

        if on_progress:
            on_progress(idx, total_specs)

    if not frames:
        raise ValueError("No se cargaron posiciones con SOURCE_SPECS.")

    return pd.concat(frames, ignore_index=True)
