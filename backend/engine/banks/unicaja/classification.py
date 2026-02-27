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
  - ``Apartado``     → A (Asset), P (Liability), AFB/PFB (Off-Balance Sheet)
  - ``Producto``     → Human-readable product name from Unicaja's core system
  - ``Epigrafe M1``  → BdE M1 regulatory heading (kept for audit, not used
                        in classification — Producto is more granular)

Rule ordering: more specific keywords are listed before broader ones so that
first-match-wins semantics produce correct results (e.g., "DEUDORES EN TARJETA"
before "CREDITO"; "VENCIDO" before "EFECTO").
"""

from __future__ import annotations

# ═════════════════════════════════════════════════════════════════════════════
# ASSET rules (Apartado = "A")
# ═════════════════════════════════════════════════════════════════════════════
# Format: (keyword_to_find_in_Producto, subcategory_id)

ASSET_RULES: list[tuple[str, str]] = [
    # ── Mortgages ─────────────────────────────────────────────────────────
    ("HIPOTECARIO",               "mortgages"),

    # ── Personal Loans (includes leasing) ─────────────────────────────────
    ("PERSONAL",                  "personal-loans"),
    ("FINANCIACION ECONOMIA",     "personal-loans"),
    ("FINANCIACION EMPRESA",      "personal-loans"),
    ("LEASING",                   "personal-loans"),

    # ── Credit Cards (behavioral — non-maturity on asset side) ────────────
    ("TARJETA",                   "credit-cards"),
    ("DEUDORES EN TARJETA",       "credit-cards"),

    # ── Credit Lines & Revolving (behavioral, includes overdrafts) ────────
    ("DESCUBIERTO",               "credit-lines"),
    ("EXCEDIDO",                  "credit-lines"),
    ("CREDITO",                   "credit-lines"),
    ("CONFIRMING",                "credit-lines"),
    ("FACTORING",                 "credit-lines"),

    # ── Non-performing → other-assets (special treatment) ─────────────────
    ("VENCIDO",                   "other-assets"),
    ("DUDOSO",                    "other-assets"),

    # ── Securities (includes commercial paper, bills, fixed-income) ───────
    ("EFECTO",                    "securities"),
    ("PAGARE",                    "securities"),
    ("ANTICIPO",                  "securities"),
    ("LETRA DEL TESORO",          "securities"),
    ("COSTE AMORTIZADO",          "securities"),
    ("VR CAMBIOS PATRIMONIO",     "securities"),
    ("VR CON CAMBIOS EN PYG",     "securities"),
    ("NEGOCIACION",               "securities"),
    ("CARTERA",                   "securities"),
    ("BONO",                      "securities"),
    ("TITULO",                    "securities"),
    ("RENTA FIJA",                "securities"),
    ("VALORES",                   "securities"),
    ("DEUDA PUBLICA",             "securities"),
    ("OBLIGACION",                "securities"),

    # ── Public Sector Lending ─────────────────────────────────────────────
    ("SECTOR PUBLICO",            "public-sector"),
    ("SINDICADO",                 "public-sector"),
    ("ADMINISTRACI",              "public-sector"),

    # ── Interbank / Central Bank ──────────────────────────────────────────
    ("INTERBANCARIO",             "interbank"),
    ("BCE",                       "interbank"),
    ("BANCO DE ESPA",             "interbank"),
    ("BANCOS CENTRALES",          "interbank"),
    ("COEFICIENTE CAJA",          "interbank"),
    ("CAJA",                      "interbank"),
    ("DEPOSITOS INTERBANCARIO",   "interbank"),
    ("CUENTAS MUTUAS",            "interbank"),
    ("CUENTAS A PLAZO ENTIDAD",   "interbank"),
    ("RESTO DEPOSITOS ENTIDAD",   "interbank"),
    ("FIANZAS ACTIVO",            "interbank"),
    ("SIMULTANEAS ACTIVAS",       "interbank"),

    # Everything else → "other-assets" (handled by classifier default)
]


# ═════════════════════════════════════════════════════════════════════════════
# LIABILITY rules (Apartado = "P")
# ═════════════════════════════════════════════════════════════════════════════

LIABILITY_RULES: list[tuple[str, str]] = [
    # ── Sight Deposits (behavioral — NMD) ─────────────────────────────────
    ("VISTA",                     "sight-deposits"),

    # ── Savings (behavioral — NMD, different beta) ────────────────────────
    ("AHORRO",                    "savings"),

    # ── Term Deposits (contractual) ───────────────────────────────────────
    ("IPF",                       "term-deposits"),
    ("IMPOSICION",                "term-deposits"),
    ("PLAZO FIJO",                "term-deposits"),
    ("PLAZO SECTOR",              "term-deposits"),

    # ── Wholesale Funding (bonds, institutional, ECB, interbank) ────────────
    ("CEDULA",                    "wholesale-funding"),
    ("SENIOR",                    "wholesale-funding"),
    ("EMISION",                   "wholesale-funding"),
    ("SUBORDINAD",                "wholesale-funding"),
    ("ENTIDADES DE CREDITO",      "wholesale-funding"),
    ("MAYORISTA",                 "wholesale-funding"),
    ("FIANZAS PASIVO",            "wholesale-funding"),
    ("DEPOSITOS INTERBANCARIO",   "wholesale-funding"),
    ("BCE",                       "wholesale-funding"),
    ("BANCO DE ESPA",             "wholesale-funding"),

    # ── Repo / Simultaneous ───────────────────────────────────────────────
    ("SIMULTANEA",                "repo-funding"),

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
    ("FWD",                       "derivatives"),
]
