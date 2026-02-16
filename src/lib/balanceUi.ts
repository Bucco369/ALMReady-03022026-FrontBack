import type {
  BalanceSheetSummary,
  BalanceSummaryResponse,
  BalanceSummaryTree,
  BalanceTreeCategory,
  BalanceTreeNode,
} from "@/lib/api";

export type BalanceUiCategory = "asset" | "liability";

export interface BalanceUiRow {
  id: string;
  sheetName: string;
  label: string;
  category: BalanceUiCategory;
  amount: number;
  positions: number;
  avgRate: number | null;
  avgMaturity: number | null;
  columns: string[];
}

export interface BalanceSubcategoryUiRow {
  id: string;
  name: string;
  amount: number;
  positions: number;
  avgRate: number | null;
  avgMaturity: number | null;
}

export interface BalanceCategoryUiTree {
  id: "assets" | "liabilities";
  name: string;
  amount: number;
  positions: number;
  avgRate: number | null;
  avgMaturity: number | null;
  subcategories: BalanceSubcategoryUiRow[];
}

export interface BalanceUiTree {
  assets: BalanceCategoryUiTree;
  liabilities: BalanceCategoryUiTree;
}

const ASSET_SUBCATEGORY_ORDER = [
  "mortgages",
  "loans",
  "securities",
  "interbank",
  "other-assets",
];

const LIABILITY_SUBCATEGORY_ORDER = [
  "deposits",
  "term-deposits",
  "wholesale-funding",
  "debt-issued",
  "other-liabilities",
];

function normalizeId(input: string): string {
  const ascii = input.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  return ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function inferCategoryFromSheetName(sheetName: string): BalanceUiCategory {
  const name = sheetName.toLowerCase();
  const liabilityTokens = [
    "acreedora",
    "acreedoras",
    "deposit",
    "imposicion",
    "pasiv",
    "liabil",
    "funding",
    "debt",
  ];

  return liabilityTokens.some((token) => name.includes(token)) ? "liability" : "asset";
}

export function mapSheetSummaryToUiRow(sheet: BalanceSheetSummary): BalanceUiRow {
  return {
    id: normalizeId(sheet.sheet),
    sheetName: sheet.sheet,
    label: sheet.sheet,
    category: inferCategoryFromSheetName(sheet.sheet),
    amount: sheet.total_saldo_ini ?? sheet.total_book_value ?? 0,
    positions: sheet.rows,
    avgRate: sheet.avg_tae,
    avgMaturity: 0,
    columns: sheet.columns,
  };
}

export function mapBalanceSummaryToUiRows(summary: BalanceSummaryResponse): BalanceUiRow[] {
  return summary.sheets.map(mapSheetSummaryToUiRow);
}

function normalizeNode(node: BalanceTreeNode): BalanceSubcategoryUiRow {
  return {
    id: node.id,
    name: node.label,
    amount: node.amount,
    positions: node.positions,
    avgRate: node.avg_rate,
    avgMaturity: node.avg_maturity,
  };
}

function sortSubcategories(nodes: BalanceSubcategoryUiRow[], order: string[]): BalanceSubcategoryUiRow[] {
  const idx = new Map(order.map((id, position) => [id, position]));
  return [...nodes].sort((a, b) => {
    const aOrder = idx.has(a.id) ? (idx.get(a.id) as number) : Number.POSITIVE_INFINITY;
    const bOrder = idx.has(b.id) ? (idx.get(b.id) as number) : Number.POSITIVE_INFINITY;
    if (aOrder !== bOrder) return aOrder - bOrder;
    return a.name.localeCompare(b.name);
  });
}

function toCategoryTree(
  category: BalanceTreeCategory | null | undefined,
  fallbackId: "assets" | "liabilities",
  fallbackName: string
): BalanceCategoryUiTree {
  return {
    id: fallbackId,
    name: category?.label ?? fallbackName,
    amount: category?.amount ?? 0,
    positions: category?.positions ?? 0,
    avgRate: category?.avg_rate ?? null,
    avgMaturity: category?.avg_maturity ?? null,
    subcategories: (category?.subcategories ?? []).map(normalizeNode),
  };
}

export function mapSummaryTreeToUiTree(summaryTree: BalanceSummaryTree | null | undefined): BalanceUiTree {
  const assets = toCategoryTree(summaryTree?.assets, "assets", "Assets");
  const liabilities = toCategoryTree(summaryTree?.liabilities, "liabilities", "Liabilities");

  return {
    assets: {
      ...assets,
      subcategories: sortSubcategories(assets.subcategories, ASSET_SUBCATEGORY_ORDER),
    },
    liabilities: {
      ...liabilities,
      subcategories: sortSubcategories(liabilities.subcategories, LIABILITY_SUBCATEGORY_ORDER),
    },
  };
}
