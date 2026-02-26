"""
Balance sheet schema definition.

SINGLE SOURCE OF TRUTH for the balance tree structure used throughout
ALMReady: backend tree building, frontend display, What-If overlays,
detail views, regulatory reporting buckets, etc.

To customize for a new client: do NOT modify this file.
Instead, create a client module in balance_config/clients/<client>.py
with classification rules that map bank products to these categories.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubcategoryDef:
    """One subcategory inside a balance category (e.g. Mortgages inside Assets)."""
    id: str
    label: str


@dataclass(frozen=True)
class CategoryDef:
    """A top-level balance category (Assets, Liabilities, Derivatives)."""
    id: str
    label: str
    subcategories: tuple[SubcategoryDef, ...]


# ═════════════════════════════════════════════════════════════════════════════
# CANONICAL BALANCE SUBCATEGORIES
# ═════════════════════════════════════════════════════════════════════════════

ASSET_SUBCATEGORIES = (
    SubcategoryDef("interbank",        "Interbank / Central Bank"),
    SubcategoryDef("mortgages",        "Mortgages"),
    SubcategoryDef("personal-loans",   "Personal Loans"),
    SubcategoryDef("public-sector",    "Public Sector Lending"),
    SubcategoryDef("credit-cards",     "Credit Cards"),
    SubcategoryDef("credit-lines",     "Credit Lines & Revolving"),
    SubcategoryDef("securities",       "Securities"),
    SubcategoryDef("other-assets",     "Other Assets"),
)

LIABILITY_SUBCATEGORIES = (
    SubcategoryDef("savings",           "Savings Accounts"),
    SubcategoryDef("sight-deposits",    "Sight Deposits"),
    SubcategoryDef("term-deposits",     "Term Deposits"),
    SubcategoryDef("wholesale-funding", "Wholesale Funding"),
    SubcategoryDef("repo-funding",      "Repo & Simultaneous"),
    SubcategoryDef("other-liabilities", "Other Liabilities"),
)

# ═════════════════════════════════════════════════════════════════════════════
# TOP-LEVEL CATEGORIES
# ═════════════════════════════════════════════════════════════════════════════

ASSETS      = CategoryDef("assets",      "Assets",      ASSET_SUBCATEGORIES)
LIABILITIES = CategoryDef("liabilities", "Liabilities", LIABILITY_SUBCATEGORIES)
DERIVATIVES = CategoryDef("derivatives", "Derivatives", ())

ALL_CATEGORIES = (ASSETS, LIABILITIES, DERIVATIVES)

# ═════════════════════════════════════════════════════════════════════════════
# DERIVED LOOKUPS (consumed by main.py, frontend, etc.)
# ═════════════════════════════════════════════════════════════════════════════

# Ordered ID lists for UI display sorting
ASSET_SUBCATEGORY_ORDER: list[str] = [s.id for s in ASSET_SUBCATEGORIES]
LIABILITY_SUBCATEGORY_ORDER: list[str] = [s.id for s in LIABILITY_SUBCATEGORIES]

# subcategory_id → display label
SUBCATEGORY_LABELS: dict[str, str] = {
    s.id: s.label
    for cat in (ASSETS, LIABILITIES)
    for s in cat.subcategories
}

# subcategory_id → parent side ("asset" | "liability")
SUBCATEGORY_SIDE: dict[str, str] = {
    **{s.id: "asset" for s in ASSET_SUBCATEGORIES},
    **{s.id: "liability" for s in LIABILITY_SUBCATEGORIES},
}

# Default subcategories when classification yields no match
ASSET_DEFAULT = "other-assets"
LIABILITY_DEFAULT = "other-liabilities"

# categoria_ui label by side (used in canonical rows)
SIDE_CATEGORIA_UI: dict[str, str] = {
    "asset": "Assets",
    "liability": "Liabilities",
    "derivative": "Derivatives",
}
