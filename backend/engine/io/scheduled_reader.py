from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from engine.io._utils import (
    mapping_attr as _mapping_attr,
    mapping_attr_optional as _mapping_attr_optional,
    norm_header as _norm_header,
    norm_token as _norm_token,
    parse_date as _parse_date,
    parse_number as _parse_number,
    resolve_glob_matches as _resolve_glob_matches,
    to_sequence as _to_sequence,
)
from engine.io.positions_reader import read_positions_dataframe, read_tabular_raw


def _resolve_column_name(df: pd.DataFrame, col: str | int, *, field_name: str) -> str:
    if isinstance(col, int):
        if col < 0 or col >= len(df.columns):
            raise ValueError(f"{field_name} index fuera de rango: {col}")
        return str(df.columns[col])
    if col not in df.columns:
        raise ValueError(f"{field_name} no existe en datos: {col!r}")
    return str(col)


def _normalise_token_set(values: Iterable[str]) -> set[str]:
    return {
        str(v).strip().lower()
        for v in values
        if v is not None and str(v).strip() != ""
    }


def _normalise_upper_token_set(values: Iterable[str]) -> set[str]:
    return {
        str(v).strip().upper()
        for v in values
        if v is not None and str(v).strip() != ""
    }


def _resolve_contract_id_source_column(raw_df: pd.DataFrame, mapping_module: Any) -> str:
    bank_columns_map = _mapping_attr(mapping_module, "BANK_COLUMNS_MAP")
    if not isinstance(bank_columns_map, Mapping):
        raise ValueError("BANK_COLUMNS_MAP debe ser Mapping.")

    norm_to_source: dict[str, str] = {}
    for col in raw_df.columns:
        norm_to_source[_norm_header(col)] = str(col)

    for source_col, canonical_col in bank_columns_map.items():
        if str(canonical_col) != "contract_id":
            continue
        key = _norm_header(source_col)
        if key in norm_to_source:
            return norm_to_source[key]

    raise ValueError(
        "No se pudo resolver la columna origen de contract_id para scheduled. "
        "Revisa BANK_COLUMNS_MAP."
    )


@dataclass
class ScheduledLoadResult:
    contracts: pd.DataFrame
    principal_flows: pd.DataFrame


def read_scheduled_tabular(
    path: str | Path,
    mapping_module: Any,
    *,
    file_type: str = "auto",
    sheet_name: str | int = 0,
    delimiter: str | None = None,
    encoding: str | None = None,
    header_row: int | None = 0,
    header_token: str | None = None,
    row_kind_column: str | int = 0,
    contract_row_kinds: Iterable[str] = ("contract",),
    payment_row_kinds: Iterable[str] = ("payment",),
    payment_type_column: str | int = 1,
    payment_date_column: str | int = 2,
    payment_amount_column: str | int = 3,
    include_payment_types: Iterable[str] | None = ("Principal",),
    strict_payment_contract_link: bool = True,
    canonical_defaults_override: Mapping[str, Any] | None = None,
    source_row_column: str = "source_row",
    reset_index: bool = True,
) -> ScheduledLoadResult:
    """
    Lector jerarquico para productos scheduled (filas contract + payment).

    - Devuelve contratos canonizados y flujos de principal enlazados por contract_id.
    - Mantiene trazabilidad por fila original via source_row.
    """

    raw_df, resolved_header_row = read_tabular_raw(
        path=path,
        file_type=file_type,
        sheet_name=sheet_name,
        delimiter=delimiter,
        encoding=encoding,
        header_row=header_row,
        header_token=header_token,
    )
    if raw_df.empty:
        empty_contracts = pd.DataFrame()
        empty_flows = pd.DataFrame(
            columns=["contract_id", "flow_type", "flow_date", "principal_amount", source_row_column]
        )
        return ScheduledLoadResult(contracts=empty_contracts, principal_flows=empty_flows)

    row_offset = int(resolved_header_row) + 2
    dayfirst = bool(_mapping_attr_optional(mapping_module, "DATE_DAYFIRST", True))

    row_kind_col = _resolve_column_name(raw_df, row_kind_column, field_name="row_kind_column")
    payment_type_col = _resolve_column_name(raw_df, payment_type_column, field_name="payment_type_column")
    payment_date_col = _resolve_column_name(raw_df, payment_date_column, field_name="payment_date_column")
    payment_amount_col = _resolve_column_name(raw_df, payment_amount_column, field_name="payment_amount_column")
    contract_id_source_col = _resolve_contract_id_source_column(raw_df, mapping_module)

    contract_kinds = _normalise_token_set(contract_row_kinds)
    payment_kinds = _normalise_token_set(payment_row_kinds)
    if not contract_kinds:
        raise ValueError("contract_row_kinds vacio para scheduled.")
    if not payment_kinds:
        raise ValueError("payment_row_kinds vacio para scheduled.")

    include_payment_types_norm = None
    if include_payment_types is not None:
        include_payment_types_norm = _normalise_upper_token_set(include_payment_types)
        if not include_payment_types_norm:
            raise ValueError("include_payment_types informado pero vacio.")

    kinds = raw_df[row_kind_col].astype("string").fillna("").str.strip().str.lower()
    contract_rows = raw_df.loc[kinds.isin(contract_kinds)].copy()
    if contract_rows.empty:
        raise ValueError("No se encontraron filas contract en scheduled.")

    contracts = read_positions_dataframe(
        contract_rows,
        mapping_module,
        row_offset=row_offset,
        canonical_defaults_override=canonical_defaults_override,
        reset_index=False,
    )
    if source_row_column:
        contracts[source_row_column] = contracts.index.to_series().astype("int64") + row_offset

    flow_records: list[dict[str, Any]] = []
    active_contract_id: str | None = None
    for idx, row in raw_df.iterrows():
        row_kind = _norm_token(row.get(row_kind_col))
        row_kind_norm = row_kind.lower() if row_kind is not None else ""

        if row_kind_norm in contract_kinds:
            active_contract_id = _norm_token(row.get(contract_id_source_col))
            continue

        if row_kind_norm not in payment_kinds:
            continue

        source_row = int(idx) + row_offset
        if active_contract_id is None:
            if strict_payment_contract_link:
                raise ValueError(
                    f"Fila payment sin contrato previo (source_row={source_row}) en scheduled."
                )
            continue

        flow_type = _norm_token(row.get(payment_type_col))
        flow_type_norm = flow_type.upper() if flow_type is not None else None
        if include_payment_types_norm is not None and flow_type_norm not in include_payment_types_norm:
            continue

        flow_date = _parse_date(row.get(payment_date_col), dayfirst=dayfirst)
        if flow_date is None:
            raise ValueError(
                f"Fecha de flujo invalida en source_row={source_row}: {row.get(payment_date_col)!r}"
            )

        principal_amount = _parse_number(row.get(payment_amount_col))
        if principal_amount is None:
            raise ValueError(
                f"Importe de flujo invalido en source_row={source_row}: {row.get(payment_amount_col)!r}"
            )

        flow_records.append(
            {
                "contract_id": active_contract_id,
                "flow_type": flow_type,
                "flow_date": flow_date,
                "principal_amount": float(principal_amount),
                source_row_column: source_row,
            }
        )

    principal_flows = pd.DataFrame(
        flow_records,
        columns=["contract_id", "flow_type", "flow_date", "principal_amount", source_row_column],
    )

    if reset_index:
        contracts = contracts.reset_index(drop=True)
        principal_flows = principal_flows.reset_index(drop=True)

    return ScheduledLoadResult(contracts=contracts, principal_flows=principal_flows)


def load_scheduled_from_specs(
    root_path: str | Path,
    mapping_module: Any,
    *,
    source_specs: Sequence[Mapping[str, Any]] | None = None,
) -> ScheduledLoadResult:
    """
    Carga scheduled desde SOURCE_SPECS con formato jerarquico contract/payment.
    """

    base_path = Path(root_path)
    if not base_path.exists():
        raise FileNotFoundError(f"No existe root_path para scheduled: {base_path}")

    specs = (
        list(source_specs)
        if source_specs is not None
        else list(_mapping_attr(mapping_module, "SOURCE_SPECS"))
    )
    if not specs:
        raise ValueError("SOURCE_SPECS vacio: define al menos una fuente scheduled.")

    contract_frames: list[pd.DataFrame] = []
    flow_frames: list[pd.DataFrame] = []

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
                result = read_scheduled_tabular(
                    path=source_file,
                    mapping_module=mapping_module,
                    file_type=file_type,
                    sheet_name=sheet,
                    delimiter=raw_spec.get("delimiter"),
                    encoding=raw_spec.get("encoding"),
                    header_row=raw_spec.get("header_row", 0),
                    header_token=raw_spec.get("header_token"),
                    row_kind_column=raw_spec.get("row_kind_column", 0),
                    contract_row_kinds=raw_spec.get("contract_row_kinds", raw_spec.get("include_row_kinds", ["contract"])),
                    payment_row_kinds=raw_spec.get("payment_row_kinds", ["payment"]),
                    payment_type_column=raw_spec.get("payment_type_column", 1),
                    payment_date_column=raw_spec.get("payment_date_column", 2),
                    payment_amount_column=raw_spec.get("payment_amount_column", 3),
                    include_payment_types=raw_spec.get("include_payment_types", ["Principal"]),
                    strict_payment_contract_link=bool(raw_spec.get("strict_payment_contract_link", True)),
                    canonical_defaults_override=defaults,
                    source_row_column="source_row",
                    reset_index=True,
                )

                contracts = result.contracts.copy()
                principal_flows = result.principal_flows.copy()

                contracts["source_spec"] = spec_name
                contracts["source_file"] = str(source_file)
                principal_flows["source_spec"] = spec_name
                principal_flows["source_file"] = str(source_file)

                if file_type.lower() == "csv":
                    contracts["source_sheet"] = pd.NA
                    principal_flows["source_sheet"] = pd.NA
                else:
                    contracts["source_sheet"] = sheet
                    principal_flows["source_sheet"] = sheet

                if "source_bank" in raw_spec:
                    contracts["source_bank"] = raw_spec.get("source_bank")
                    principal_flows["source_bank"] = raw_spec.get("source_bank")
                if "source_contract_type" in raw_spec:
                    contracts["source_contract_type"] = raw_spec.get("source_contract_type")
                    principal_flows["source_contract_type"] = raw_spec.get("source_contract_type")

                contract_frames.append(contracts)
                flow_frames.append(principal_flows)

    if not contract_frames:
        raise ValueError("No se cargaron contratos scheduled con SOURCE_SPECS.")

    contracts_out = pd.concat(contract_frames, ignore_index=True)
    if flow_frames:
        flows_out = pd.concat(flow_frames, ignore_index=True)
    else:
        flows_out = pd.DataFrame(
            columns=[
                "contract_id",
                "flow_type",
                "flow_date",
                "principal_amount",
                "source_row",
                "source_spec",
                "source_file",
                "source_sheet",
            ]
        )

    return ScheduledLoadResult(contracts=contracts_out, principal_flows=flows_out)
