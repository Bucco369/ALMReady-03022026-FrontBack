"""Domain constants and balance_config re-exports."""

from __future__ import annotations

from engine.balance_config.schema import (
    ASSET_SUBCATEGORY_ORDER,
    LIABILITY_SUBCATEGORY_ORDER,
    SUBCATEGORY_LABELS as _BC_LABELS,
    SIDE_CATEGORIA_UI as _BC_SIDE_UI,
)
from engine.balance_config.classifier import classify_position as _bc_classify
from engine.balance_config.clients import get_client_rules as _bc_get_rules

# Excel sheets that are metadata/schema – skip during parsing.
META_SHEETS = {
    "README",
    "SCHEMA_BASE",
    "SCHEMA_DERIV",
    "BALANCE_CHECK",
    "BALANCE_SUMMARY",
    "CURVES_ENUMS",
}

# Only sheets starting with these prefixes contain position data.
POSITION_PREFIXES = ("A_", "L_", "E_", "D_")

# Columns that MUST exist in every A_, L_, E_ sheet.
BASE_REQUIRED_COLS = {
    "num_sec_ac",
    "lado_balance",
    "categoria_ui",
    "subcategoria_ui",
    "grupo",
    "moneda",
    "saldo_ini",
    "tipo_tasa",
}

# Legacy alias map — used by the Excel upload path.
# Maps human-readable labels (lowercased) to canonical subcategory IDs.
SUBCATEGORY_ID_ALIASES = {
    # Current canonical IDs (identity mapping)
    "interbank": "interbank",
    "mortgages": "mortgages",
    "personal-loans": "personal-loans",
    "public-sector": "public-sector",
    "credit-cards": "credit-cards",
    "credit-lines": "credit-lines",
    "securities": "securities",
    "other-assets": "other-assets",
    "savings": "savings",
    "sight-deposits": "sight-deposits",
    "term-deposits": "term-deposits",
    "wholesale-funding": "wholesale-funding",
    "repo-funding": "repo-funding",
    "other-liabilities": "other-liabilities",
    # Legacy aliases (old schema → new schema)
    "loans": "personal-loans",
    "leasing": "personal-loans",
    "commercial-paper": "securities",
    "securities-ac": "securities",
    "securities-fvoci": "securities",
    "overdrafts": "credit-lines",
    "non-performing": "other-assets",
    "interbank / central bank": "interbank",
    "other assets": "other-assets",
    "deposits": "sight-deposits",
    "term deposits": "term-deposits",
    "covered-bonds": "wholesale-funding",
    "senior-debt": "wholesale-funding",
    "subordinated-debt": "wholesale-funding",
    "ecb-funding": "wholesale-funding",
    "wholesale funding": "wholesale-funding",
    "debt issued": "wholesale-funding",
    "other liabilities": "other-liabilities",
    "equity": "equity",
}

# Motor source_contract_type → UI labels.
_CONTRACT_TYPE_LABELS = {
    "fixed_annuity": "Fixed Annuity",
    "fixed_bullet": "Fixed Bullet",
    "fixed_linear": "Fixed Linear",
    "fixed_non_maturity": "Non-Maturity (Fixed)",
    "fixed_scheduled": "Fixed Scheduled",
    "variable_annuity": "Variable Annuity",
    "variable_bullet": "Variable Bullet",
    "variable_linear": "Variable Linear",
    "variable_non_maturity": "Non-Maturity (Variable)",
    "variable_scheduled": "Variable Scheduled",
}
