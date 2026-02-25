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
SUBCATEGORY_ID_ALIASES = {
    "mortgages": "mortgages",
    "loans": "loans",
    "securities": "securities",
    "interbank / central bank": "interbank",
    "other assets": "other-assets",
    "deposits": "deposits",
    "term deposits": "term-deposits",
    "wholesale funding": "wholesale-funding",
    "debt issued": "debt-issued",
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

# ── What-If maps ────────────────────────────────────────────────────────────

_PRODUCT_TEMPLATE_TO_MOTOR = {
    "fixed-loan":     {"source_contract_type": "fixed_annuity",   "side": "A"},
    "floating-loan":  {"source_contract_type": "variable_bullet", "side": "A"},
    "bond-portfolio": {"source_contract_type": "fixed_bullet",    "side": "A"},
    "securitised":    {"source_contract_type": "fixed_annuity",   "side": "A"},
    "term-deposit":   {"source_contract_type": "fixed_bullet",    "side": "L"},
    "wholesale":      {"source_contract_type": "fixed_bullet",    "side": "L"},
    "irs-hedge":      {"source_contract_type": "fixed_bullet",    "side": "A"},
}

_CATEGORY_SIDE_MAP = {"asset": "A", "liability": "L", "derivative": "A"}

_FREQ_TO_MONTHS = {
    "monthly": 1, "quarterly": 3, "semi-annual": 6, "annual": 12,
}

_REF_INDEX_TO_MOTOR: dict[str, str] = {
    "EURIBOR 3M":  "EUR_EURIBOR_3M",
    "EURIBOR 6M":  "EUR_EURIBOR_6M",
    "EURIBOR 12M": "EUR_EURIBOR_12M",
    "SOFR":        "USD_SOFR",
    "SONIA":       "GBP_SONIA",
}
