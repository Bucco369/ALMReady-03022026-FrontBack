"""
Mapping Unicaja -> canonico ALMReady.

Disenado para cargar automaticamente los CSV de:
  ../data/fixtures/positions/unicaja
"""

from __future__ import annotations


# Required/optional are tuned for mixed products including non-maturity.
REQUIRED_CANONICAL_COLUMNS = (
    "contract_id",
    "start_date",
    "notional",
    "side",
    "rate_type",
    "daycount_base",
)

OPTIONAL_CANONICAL_COLUMNS = (
    "maturity_date",
    "index_name",
    "spread",
    "fixed_rate",
    "repricing_freq",
    "payment_freq",
    # Solo para variable_annuity:
    # - "reprice_on_reset" (default legacy)
    # - "fixed_payment"
    # Si no viene en fichero, puede definirse en DEFAULT_CANONICAL_VALUES
    # o via parametro global `variable_annuity_payment_mode` del pipeline.
    "annuity_payment_mode",
    "next_reprice_date",
    "floor_rate",
    "cap_rate",
    # Balance classification columns (used by balance_config classifier).
    # These are read from the bank's CSV but NOT used by the motor —
    # only by _canonicalize_motor_row() to assign subcategory_id.
    "balance_product",
    "balance_section",
    "balance_epigrafe",
)


BANK_COLUMNS_MAP = {
    "Identifier": "contract_id",
    "Start date": "start_date",
    "Maturity date": "maturity_date",
    "Outstanding principal": "notional",
    "Position": "side",
    "Day count convention": "daycount_base",
    "Indexed curve": "index_name",
    "Interest spread": "spread",
    "Indexed rate": "fixed_rate",
    "Last adjusted rate": "fixed_rate",
    "Reset period": "repricing_freq",
    "Payment period": "payment_freq",
    "Interest payment period": "payment_freq",
    # Si el banco aporta una columna de modo de cuota para variable_annuity,
    # mapearla aqui a `annuity_payment_mode`.
    "Annuity Payment Mode": "annuity_payment_mode",
    "Reset anchor date": "next_reprice_date",
    "Interest rate floor": "floor_rate",
    "Interest rate cap": "cap_rate",
    # Balance classification columns (→ balance_config classifier)
    "Producto": "balance_product",
    "Apartado": "balance_section",
    "Epigrafe M1": "balance_epigrafe",
}


SIDE_MAP = {
    "LONG": "A",
    "SHORT": "L",
}


RATE_TYPE_MAP = {
    "FIXED": "fixed",
    "FLOAT": "float",
    "FLOATING": "float",
    "VARIABLE": "float",
    "VAR": "float",
    # For generic integrations where source passes these directly.
    "FIX": "fixed",
}


DATE_DAYFIRST = True

# Unicaja rates come in percentage points (e.g. 2.50 means 2.50%).
NUMERIC_SCALE_MAP = {
    "spread": 0.01,
    "fixed_rate": 0.01,
    "floor_rate": 0.01,
    "cap_rate": 0.01,
}


DEFAULT_CANONICAL_VALUES = {
    # Ejemplo de activacion global por banco:
    # "annuity_payment_mode": "fixed_payment",
}

INDEX_NAME_ALIASES = {
    # Common encoding variants for Ñ in some exports.
    "DEUDA_ESPA�OLA": "DEUDA_ESPAÑOLA",
    "DEUDA_ESPAï¿½OLA": "DEUDA_ESPAÑOLA",
    "DEUDA_ESPA?OLA": "DEUDA_ESPAÑOLA",
}

PRESERVE_UNMAPPED_COLUMNS = False
UNMAPPED_PREFIX = "extra_"


_CSV_COMMON = {
    "file_type": "csv",
    "delimiter": ";",
    "encoding": "cp1252",
    "header_token": "Identifier",
    "source_bank": "unicaja",
}


SOURCE_SPECS = [
    {
        **_CSV_COMMON,
        "name": "fixed_annuity",
        "pattern": "Fixed annuity.csv",
        "defaults": {"rate_type": "fixed"},
        "source_contract_type": "fixed_annuity",
    },
    {
        **_CSV_COMMON,
        "name": "fixed_bullet",
        "pattern": "Fixed bullet.csv",
        "row_kind_column": 0,
        "include_row_kinds": ["contract"],
        "defaults": {"rate_type": "fixed"},
        "source_contract_type": "fixed_bullet",
    },
    {
        **_CSV_COMMON,
        "name": "fixed_linear",
        "pattern": "Fixed linear.csv",
        "defaults": {"rate_type": "fixed"},
        "source_contract_type": "fixed_linear",
    },
    {
        **_CSV_COMMON,
        "name": "fixed_scheduled",
        "pattern": "Fixed scheduled.csv",
        "row_kind_column": 0,
        "include_row_kinds": ["contract"],
        "defaults": {"rate_type": "fixed"},
        "source_contract_type": "fixed_scheduled",
    },
    {
        **_CSV_COMMON,
        "name": "fixed_non_maturity",
        "pattern": "Non-maturity.csv",
        "defaults": {"rate_type": "fixed"},
        "source_contract_type": "fixed_non_maturity",
    },
    {
        **_CSV_COMMON,
        "name": "variable_annuity",
        "pattern": "Variable annuity.csv",
        "row_kind_column": 0,
        "include_row_kinds": ["contract"],
        "defaults": {"rate_type": "float"},
        "source_contract_type": "variable_annuity",
    },
    {
        **_CSV_COMMON,
        "name": "variable_bullet",
        "pattern": "Variable bullet.csv",
        "row_kind_column": 0,
        "include_row_kinds": ["contract"],
        "defaults": {"rate_type": "float"},
        "source_contract_type": "variable_bullet",
    },
    {
        **_CSV_COMMON,
        "name": "variable_linear",
        "pattern": "Variable linear.csv",
        "defaults": {"rate_type": "float"},
        "source_contract_type": "variable_linear",
    },
    {
        **_CSV_COMMON,
        "name": "variable_non_maturity",
        "pattern": "Variable non-maturity.csv",
        "defaults": {"rate_type": "float"},
        "source_contract_type": "variable_non_maturity",
    },
    {
        **_CSV_COMMON,
        "name": "variable_scheduled",
        "pattern": "Variable scheduled.csv",
        "row_kind_column": 0,
        "include_row_kinds": ["contract"],
        "defaults": {"rate_type": "float"},
        "source_contract_type": "variable_scheduled",
    },
    # Deliberately excluded for now: Static_position.csv
    # It lacks key cashflow fields (start/maturity/daycount) needed for NII pipelines.
]
