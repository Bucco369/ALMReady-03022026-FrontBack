/**
 * balanceSchema.ts – Single source of truth for balance tree structure.
 *
 * Mirrors backend/almready/balance_config/schema.py.
 * All balance-related UI (tree display, detail labels, What-If overlays,
 * subcategory ordering) should import from here instead of hardcoding.
 *
 * To customize for a new client: only this file and the backend
 * balance_config/clients/<client>.py need to change.
 */

// ═════════════════════════════════════════════════════════════════════════════
// Types
// ═════════════════════════════════════════════════════════════════════════════

export interface SubcategoryDef {
  id: string;
  label: string;
}

export interface CategoryDef {
  id: string;
  label: string;
  subcategories: SubcategoryDef[];
}

// ═════════════════════════════════════════════════════════════════════════════
// Canonical balance subcategories
// ═════════════════════════════════════════════════════════════════════════════

export const ASSET_SUBCATEGORIES: SubcategoryDef[] = [
  { id: "mortgages",    label: "Mortgages" },
  { id: "loans",        label: "Loans" },
  { id: "securities",   label: "Securities" },
  { id: "interbank",    label: "Interbank / Central Bank" },
  { id: "other-assets", label: "Other assets" },
];

export const LIABILITY_SUBCATEGORIES: SubcategoryDef[] = [
  { id: "deposits",          label: "Deposits" },
  { id: "term-deposits",     label: "Term deposits" },
  { id: "wholesale-funding", label: "Wholesale funding" },
  { id: "debt-issued",       label: "Debt issued" },
  { id: "other-liabilities", label: "Other liabilities" },
];

// ═════════════════════════════════════════════════════════════════════════════
// Top-level categories
// ═════════════════════════════════════════════════════════════════════════════

export const ASSETS: CategoryDef = {
  id: "assets",
  label: "Assets",
  subcategories: ASSET_SUBCATEGORIES,
};

export const LIABILITIES: CategoryDef = {
  id: "liabilities",
  label: "Liabilities",
  subcategories: LIABILITY_SUBCATEGORIES,
};

// ═════════════════════════════════════════════════════════════════════════════
// Derived lookups
// ═════════════════════════════════════════════════════════════════════════════

/** Ordered ID lists for UI display sorting */
export const ASSET_SUBCATEGORY_ORDER: string[] =
  ASSET_SUBCATEGORIES.map((s) => s.id);

export const LIABILITY_SUBCATEGORY_ORDER: string[] =
  LIABILITY_SUBCATEGORIES.map((s) => s.id);

/** subcategory_id → display label */
export const SUBCATEGORY_LABELS: Record<string, string> = Object.fromEntries([
  ...ASSET_SUBCATEGORIES.map((s) => [s.id, s.label]),
  ...LIABILITY_SUBCATEGORIES.map((s) => [s.id, s.label]),
]);

/**
 * Context labels for the detail modal.
 * Maps subcategory_id → "Category → Subcategory" breadcrumb.
 */
export const DETAIL_CONTEXT_LABELS: Record<string, string> = {
  assets: "Assets",
  liabilities: "Liabilities",
  ...Object.fromEntries(
    ASSET_SUBCATEGORIES.map((s) => [s.id, `Assets → ${s.label}`])
  ),
  ...Object.fromEntries(
    LIABILITY_SUBCATEGORIES.map((s) => [s.id, `Liabilities → ${s.label}`])
  ),
};
