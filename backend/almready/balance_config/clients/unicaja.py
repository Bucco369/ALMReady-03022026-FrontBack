"""
Unicaja – Balance classification rules.

Maps Unicaja's ``Producto`` column to canonical balance subcategories.
Rules are evaluated in order — first keyword match wins.

Maintenance guide:
  - To add a product   → add a line to the appropriate *_RULES list.
  - To reclassify      → move the keyword to a different category.
  - To add a category  → first add it in balance_config/schema.py,
                          then reference the new id here.

Data source columns used:
  - ``Apartado``     → A (Activo), P (Pasivo), AFB/PFB (Fuera de Balance)
  - ``Producto``     → Human-readable product name from Unicaja's core system
  - ``Epigrafe M1``  → BdE M1 regulatory heading (kept for audit, not used
                        in classification — Producto is more granular)
"""

from __future__ import annotations

# ═════════════════════════════════════════════════════════════════════════════
# ASSET rules (Apartado = "A")
# ═════════════════════════════════════════════════════════════════════════════
# Format: (keyword_to_find_in_Producto, subcategory_id)

ASSET_RULES: list[tuple[str, str]] = [
    # ── Mortgages ─────────────────────────────────────────────────────────
    # All mortgage products (hipotecarios): direct purchase, subrogation,
    # agricultural, commercial, mixed-rate, etc.
    ("HIPOTECARIO",               "mortgages"),

    # ── Loans ─────────────────────────────────────────────────────────────
    # Personal loans, credit lines, cards, overdrafts, leasing, etc.
    ("PERSONAL",                  "loans"),
    ("CREDITO",                   "loans"),
    ("EFECTO",                    "loans"),
    ("CONFIRMING",                "loans"),
    ("TARJETA",                   "loans"),
    ("DESCUBIERTO",               "loans"),
    ("VENCIDO",                   "loans"),
    ("SINDICADO",                 "loans"),
    ("LEASING",                   "loans"),
    ("ANTICIPO",                  "loans"),
    ("FACTORING",                 "loans"),

    # ── Securities ────────────────────────────────────────────────────────
    # Fixed-income portfolio, public debt, corporate bonds, etc.
    ("CARTERA",                   "securities"),
    ("BONO",                      "securities"),
    ("TITULO",                    "securities"),
    ("DEUDA PUBLICA",             "securities"),
    ("OBLIGACION",                "securities"),
    ("LETRA DEL TESORO",          "securities"),
    ("PAGARE",                    "securities"),
    ("RENTA FIJA",                "securities"),
    ("VALORES",                   "securities"),

    # ── Interbank / Central Bank ──────────────────────────────────────────
    # Public sector lending, interbank, central bank reserves
    ("SECTOR PUBLICO",            "interbank"),
    ("ADMINISTRACI",              "interbank"),
    ("INTERBANCARIO",             "interbank"),
    ("BCE",                       "interbank"),
    ("BANCO DE ESPA",             "interbank"),

    # Everything else → "other-assets" (handled by classifier default)
]


# ═════════════════════════════════════════════════════════════════════════════
# LIABILITY rules (Apartado = "P")
# ═════════════════════════════════════════════════════════════════════════════

LIABILITY_RULES: list[tuple[str, str]] = [
    # ── Deposits ──────────────────────────────────────────────────────────
    # Demand deposits (cuentas vista) and savings accounts (ahorro)
    ("VISTA",                     "deposits"),
    ("AHORRO",                    "deposits"),

    # ── Term deposits ─────────────────────────────────────────────────────
    # IPF (Imposiciones a Plazo Fijo) and other fixed-term retail deposits
    ("IPF",                       "term-deposits"),
    ("IMPOSICION",                "term-deposits"),
    ("PLAZO FIJO",                "term-deposits"),

    # ── Wholesale funding ─────────────────────────────────────────────────
    # Interbank borrowing, ECB, institutional funding
    ("ENTIDADES DE CREDITO",      "wholesale-funding"),
    ("MAYORISTA",                 "wholesale-funding"),
    ("INTERBANCARIO",             "wholesale-funding"),
    ("BCE",                       "wholesale-funding"),
    ("BANCO DE ESPA",             "wholesale-funding"),

    # ── Debt issued ───────────────────────────────────────────────────────
    # Covered bonds (cédulas), senior bonds, subordinated debt, etc.
    ("CEDULA",                    "debt-issued"),
    ("EMISION",                   "debt-issued"),
    ("SENIOR",                    "debt-issued"),
    ("SUBORDINAD",                "debt-issued"),
    ("BONO",                      "debt-issued"),

    # Everything else → "other-liabilities" (handled by classifier default)
]


# ═════════════════════════════════════════════════════════════════════════════
# DERIVATIVE rules (Apartado = "AFB" or "PFB")
# ═════════════════════════════════════════════════════════════════════════════

DERIVATIVE_RULES: list[tuple[str, str]] = [
    ("SWAP",                      "derivatives"),
    ("OPCION",                    "derivatives"),
    ("FUTURO",                    "derivatives"),
    ("FORWARD",                   "derivatives"),
    ("FRA",                       "derivatives"),
    ("CAP",                       "derivatives"),
    ("FLOOR",                     "derivatives"),
    ("SWAPTION",                  "derivatives"),
]
