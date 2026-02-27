"""Unicaja What-If product templates and reference index mappings.

These maps are bank-specific because they define:
  - Which motor contract types back each UI product template.
  - Which reference indices are available (and how they map to motor curve IDs).
  - The default risk-free discount index for this bank's currency.
"""

from __future__ import annotations

# Maps UI productTemplateId → motor contract type + default side.
PRODUCT_TEMPLATE_TO_MOTOR = {
    "fixed-loan":     {"source_contract_type": "fixed_annuity",   "side": "A"},
    "floating-loan":  {"source_contract_type": "variable_bullet", "side": "A"},
    "bond-portfolio": {"source_contract_type": "fixed_bullet",    "side": "A"},
    "securitised":    {"source_contract_type": "fixed_annuity",   "side": "A"},
    "term-deposit":   {"source_contract_type": "fixed_bullet",    "side": "L"},
    "wholesale":      {"source_contract_type": "fixed_bullet",    "side": "L"},
    "irs-hedge":      {"source_contract_type": "fixed_bullet",    "side": "A"},
}

# Maps UI category → motor side code.
CATEGORY_SIDE_MAP = {"asset": "A", "liability": "L", "derivative": "A"}

# Maps UI frequency label → number of months.
FREQ_TO_MONTHS = {
    "monthly": 1, "quarterly": 3, "semi-annual": 6, "annual": 12,
}

# Maps UI reference index label → motor curve ID.
REF_INDEX_TO_MOTOR: dict[str, str] = {
    "EURIBOR 3M":  "EUR_EURIBOR_3M",
    "EURIBOR 6M":  "EUR_EURIBOR_6M",
    "EURIBOR 12M": "EUR_EURIBOR_12M",
    "SOFR":        "USD_SOFR",
    "SONIA":       "GBP_SONIA",
}

# Default risk-free discount index for this bank's primary currency (EUR).
DEFAULT_DISCOUNT_INDEX = "EUR_ESTR_OIS"
