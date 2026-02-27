"""
Template for bank -> ALMReady canonical schema mapping.

Each bank can copy this file to:
  engine/config/bank_mapping_<bank>.py
and adjust dictionaries/config without touching the engine.
"""

from __future__ import annotations


# ============================================================================
# Canonical schema
# ============================================================================

# Minimum canonical fields for NII (MVP).
REQUIRED_CANONICAL_COLUMNS = (
    "contract_id",
    "start_date",
    "maturity_date",
    "notional",
    "side",
    "rate_type",
    "daycount_base",
)

# Optional fields prepared for future iterations.
# `annuity_payment_mode` applies only to `source_contract_type=variable_annuity`.
# Allowed values per contract:
# - "reprice_on_reset": legacy/default mode (recalculates payment at each reset)
# - "fixed_payment": fixed payment during the cycle
# Priority:
# 1) value provided in the row (`annuity_payment_mode`)
# 2) global run parameter (`variable_annuity_payment_mode`)
# 3) engine fallback: "reprice_on_reset"
OPTIONAL_CANONICAL_COLUMNS = (
    "index_name",
    "spread",
    "fixed_rate",
    "repricing_freq",
    "payment_freq",
    "annuity_payment_mode",
    "next_reprice_date",
    "floor_rate",
    "cap_rate",
    # Balance classification columns — used by app-level canonicalization
    # to map motor positions into UI categories/subcategories.
    "balance_product",
    "balance_section",
    "balance_epigrafe",
)

# Input columns -> canonical.
BANK_COLUMNS_MAP = {
    "Contract ID": "contract_id",
    "Start Date": "start_date",
    "Maturity Date": "maturity_date",
    "Notional": "notional",
    "Side": "side",
    "Rate Type": "rate_type",
    "Index Name": "index_name",
    "Spread": "spread",
    "Fixed Rate": "fixed_rate",
    "Day Count": "daycount_base",
    "Repricing Freq": "repricing_freq",
    "Payment Freq": "payment_freq",
    "Annuity Payment Mode": "annuity_payment_mode",
    "Next Reprice Date": "next_reprice_date",
    "Floor Rate": "floor_rate",
    "Cap Rate": "cap_rate",
}

# Normalize side -> canonical {A, L}.
SIDE_MAP = {
    "A": "A",
    "ASSET": "A",
    "ACTIVO": "A",
    "LONG": "A",
    "L": "L",
    "LIABILITY": "L",
    "PASIVO": "L",
    "SHORT": "L",
}

# Normalize rate type -> canonical {fixed, float}.
RATE_TYPE_MAP = {
    "FIXED": "fixed",
    "FIJO": "fixed",
    "FLOAT": "float",
    "FLOATING": "float",
    "VARIABLE": "float",
    "VAR": "float",
}


# ============================================================================
# Optional parser controls (for scalability)
# ============================================================================

# Day-first parse for ambiguous date strings.
DATE_DAYFIRST = True

# Scale factors applied AFTER numeric parsing on canonical columns.
# Example for banks where rates are in percentage points (2.5 means 2.5%):
#   {"spread": 0.01, "fixed_rate": 0.01, "floor_rate": 0.01, "cap_rate": 0.01}
NUMERIC_SCALE_MAP = {}

# Default canonical values injected when source column is missing/blank.
# Example:
#   {"daycount_base": "ACT/360", "rate_type": "fixed"}
# To force a mode per bank without touching code:
#   {"annuity_payment_mode": "fixed_payment"}
# (if a per-row value is provided, the row value takes precedence).
DEFAULT_CANONICAL_VALUES = {}

# Optional aliases to normalize index names from positions to curve names.
# Example:
#   {"EURIBOR_SWAP_MAS_0,025": "EURIBOR_SWAP_PLUS_0,025"}
INDEX_NAME_ALIASES = {}

# Keep unmapped source columns for lineage/diagnostics.
PRESERVE_UNMAPPED_COLUMNS = False
UNMAPPED_PREFIX = "extra_"


# ============================================================================
# Optional multi-source loader specs
# ============================================================================

# Declarative source config used by io.positions_pipeline.load_positions_from_specs.
# Fill this list per bank to auto-load folders/files/sheets without custom code.
#
# SOURCE_SPECS = [
#     {
#         "name": "example_contracts",
#         "pattern": "*.csv",
#         "file_type": "csv",         # or "excel" or "auto"
#         "header_token": "Identifier",
#         "delimiter": ";",
#         "encoding": "cp1252",
#         "row_kind_column": 0,       # int index or column name
#         "include_row_kinds": ["contract"],
#         "defaults": {"daycount_base": "ACT/360"},
#         "source_bank": "example_bank",
#     },
#     {
#         "name": "example_xlsx",
#         "pattern": "Extract*.xlsx",
#         "file_type": "excel",
#         "sheet_names": ["Loans", "Deposits"],  # or "sheet_name": "Loans"
#         "header_row": 0,
#         "defaults": {"side": "A"},
#     },
# ]
SOURCE_SPECS = []

# Note on scheduled (hierarchical reader):
# For files with `contract` + `payment` rows, use
# io.scheduled_reader.load_scheduled_from_specs with specs like:
# {
#   "name": "fixed_scheduled",
#   "pattern": "Fixed scheduled.csv",
#   "file_type": "csv",
#   "header_token": "Identifier",
#   "delimiter": ";",
#   "encoding": "cp1252",
#   "row_kind_column": 0,
#   "contract_row_kinds": ["contract"],     # opcional, default
#   "payment_row_kinds": ["payment"],       # opcional, default
#   "payment_type_column": 1,               # opcional, default
#   "payment_date_column": 2,               # opcional, default
#   "payment_amount_column": 3,             # opcional, default
#   "include_payment_types": ["Principal"], # opcional, default
# }
