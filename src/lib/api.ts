/**
 * api.ts – HTTP client and TypeScript types mirroring the backend API models.
 *
 * === ROLE IN THE SYSTEM ===
 * This is the SOLE communication layer between frontend and backend.
 * Every API call goes through the generic http<T>() helper which handles
 * URL construction, error extraction, and JSON parsing.
 *
 * === TYPE MIRRORING ===
 * The types here (SessionMeta, BalanceSummaryResponse, CurvePoint, etc.)
 * mirror the Pydantic models in backend/app/main.py. They MUST stay in sync.
 * When the backend adds new fields (e.g. flow_type, balance_format), they
 * should be added here too.
 *
 * === FUTURE ADDITIONS (Phase 1) ===
 * - calculateEveNii(sessionId, request): POST /api/sessions/{id}/calculate
 *   Will send {discount_curve_id, scenarios[], what_if_modifications[],
 *   behavioural_params} and return CalculationResults.
 * - uploadBalanceZip(sessionId, file): POST /api/sessions/{id}/balance/zip
 *   For ZIP→CSV input format.
 * - getCalculationResults(sessionId): GET /api/sessions/{id}/results
 *   For retrieving cached results on page refresh.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Generic HTTP helper. All API calls flow through here. */
async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} on ${path}: ${text}`);
  }
  return (await res.json()) as T;
}

export type SessionMeta = {
  session_id: string;
  created_at: string;
  status: "active" | string;
  schema_version: string;
};

export type BalanceSheetSummary = {
  sheet: string;
  rows: number;
  columns: string[];
  total_saldo_ini: number | null;
  total_book_value: number | null;
  avg_tae: number | null;
};

export type BalanceTreeNode = {
  id: string;
  label: string;
  amount: number;
  positions: number;
  avg_rate: number | null;
  avg_maturity: number | null;
};

export type BalanceTreeCategory = {
  id: string;
  label: string;
  amount: number;
  positions: number;
  avg_rate: number | null;
  avg_maturity: number | null;
  subcategories: BalanceTreeNode[];
};

export type BalanceSummaryTree = {
  assets: BalanceTreeCategory | null;
  liabilities: BalanceTreeCategory | null;
  equity: BalanceTreeCategory | null;
  derivatives: BalanceTreeCategory | null;
};

export type BalanceSummaryResponse = {
  session_id: string;
  filename: string;
  uploaded_at: string;
  sheets: BalanceSheetSummary[];
  sample_rows: Record<string, Record<string, unknown>[]>;
  summary_tree: BalanceSummaryTree;
};

export type BalanceContract = {
  contract_id: string;
  sheet: string | null;
  category: "asset" | "liability" | string;
  categoria_ui: string | null;
  subcategory: string;
  subcategoria_ui: string | null;
  group: string | null;
  currency: string | null;
  counterparty: string | null;
  rate_type: string | null;
  maturity_bucket: string | null;
  maturity_years: number | null;
  amount: number | null;
  rate: number | null;
};

export type BalanceContractsResponse = {
  session_id: string;
  total: number;
  page: number;
  page_size: number;
  contracts: BalanceContract[];
};

export type CurvePoint = {
  tenor: string;
  t_years: number;
  rate: number;
};

export type CurveCatalogItem = {
  curve_id: string;
  currency: string | null;
  label_tech: string;
  points_count: number;
  min_t: number | null;
  max_t: number | null;
};

export type CurvesSummaryResponse = {
  session_id: string;
  filename: string;
  uploaded_at: string;
  default_discount_curve_id: string | null;
  curves: CurveCatalogItem[];
};

export type CurvePointsResponse = {
  session_id: string;
  curve_id: string;
  points: CurvePoint[];
};

export type FacetOption = {
  value: string;
  count: number;
};

export type BalanceDetailsFacets = {
  currencies: FacetOption[];
  rate_types: FacetOption[];
  counterparties: FacetOption[];
  maturities: FacetOption[];
};

export type BalanceDetailsGroup = {
  group: string;
  amount: number;
  positions: number;
  avg_rate: number | null;
  avg_maturity: number | null;
};

export type BalanceDetailsTotals = {
  amount: number;
  positions: number;
  avg_rate: number | null;
  avg_maturity: number | null;
};

export type BalanceDetailsResponse = {
  session_id: string;
  categoria_ui: string | null;
  subcategoria_ui: string | null;
  groups: BalanceDetailsGroup[];
  totals: BalanceDetailsTotals;
  facets: BalanceDetailsFacets;
};

export type BalanceDetailsQuery = {
  categoria_ui?: string;
  subcategoria_ui?: string;
  subcategory_id?: string;
  currency?: string[];
  rate_type?: string[];
  counterparty?: string[];
  maturity?: string[];
};

export type BalanceContractsQuery = {
  query?: string;
  q?: string;
  categoria_ui?: string;
  subcategoria_ui?: string;
  subcategory_id?: string;
  group?: string[];
  currency?: string[];
  rate_type?: string[];
  counterparty?: string[];
  maturity?: string[];
  page?: number;
  page_size?: number;
  offset?: number;
  limit?: number;
};

function appendListParam(qs: URLSearchParams, key: string, values?: string[]) {
  if (!values || values.length === 0) return;
  qs.set(key, values.join(","));
}

export async function health(): Promise<{ status: string }> {
  return http<{ status: string }>("/api/health");
}

export async function createSession(): Promise<SessionMeta> {
  return http<SessionMeta>("/api/sessions", { method: "POST" });
}

export async function getSession(sessionId: string): Promise<SessionMeta> {
  return http<SessionMeta>(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export async function uploadBalanceExcel(sessionId: string, file: File): Promise<BalanceSummaryResponse> {
  const fd = new FormData();
  fd.append("file", file, file.name);

  return http<BalanceSummaryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/balance`,
    { method: "POST", body: fd }
  );
}

export async function getBalanceSummary(sessionId: string): Promise<BalanceSummaryResponse> {
  return http<BalanceSummaryResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/balance/summary`);
}

export async function uploadCurvesExcel(sessionId: string, file: File): Promise<CurvesSummaryResponse> {
  const fd = new FormData();
  fd.append("file", file, file.name);

  return http<CurvesSummaryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/curves`,
    { method: "POST", body: fd }
  );
}

export async function getCurvesSummary(sessionId: string): Promise<CurvesSummaryResponse> {
  return http<CurvesSummaryResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/curves/summary`);
}

export async function getCurvePoints(sessionId: string, curveId: string): Promise<CurvePointsResponse> {
  return http<CurvePointsResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/curves/${encodeURIComponent(curveId)}`
  );
}

export async function getBalanceDetails(
  sessionId: string,
  params?: BalanceDetailsQuery
): Promise<BalanceDetailsResponse> {
  const qs = new URLSearchParams();
  if (params?.categoria_ui) qs.set("categoria_ui", params.categoria_ui);
  if (params?.subcategoria_ui) qs.set("subcategoria_ui", params.subcategoria_ui);
  if (params?.subcategory_id) qs.set("subcategory_id", params.subcategory_id);
  appendListParam(qs, "currency", params?.currency);
  appendListParam(qs, "rate_type", params?.rate_type);
  appendListParam(qs, "counterparty", params?.counterparty);
  appendListParam(qs, "maturity", params?.maturity);

  const query = qs.toString();
  const path = `/api/sessions/${encodeURIComponent(sessionId)}/balance/details${query ? `?${query}` : ""}`;
  return http<BalanceDetailsResponse>(path);
}

export async function getBalanceContracts(
  sessionId: string,
  params?: BalanceContractsQuery
): Promise<BalanceContractsResponse> {
  const qs = new URLSearchParams();
  if (params?.query) qs.set("query", params.query);
  else if (params?.q) qs.set("q", params.q);
  if (params?.categoria_ui) qs.set("categoria_ui", params.categoria_ui);
  if (params?.subcategoria_ui) qs.set("subcategoria_ui", params.subcategoria_ui);
  if (params?.subcategory_id) qs.set("subcategory_id", params.subcategory_id);
  appendListParam(qs, "group", params?.group);
  appendListParam(qs, "currency", params?.currency);
  appendListParam(qs, "rate_type", params?.rate_type);
  appendListParam(qs, "counterparty", params?.counterparty);
  appendListParam(qs, "maturity", params?.maturity);
  if (params?.page !== undefined) qs.set("page", String(params.page));
  if (params?.page_size !== undefined) qs.set("page_size", String(params.page_size));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));

  const query = qs.toString();
  const path = `/api/sessions/${encodeURIComponent(sessionId)}/balance/contracts${query ? `?${query}` : ""}`;
  return http<BalanceContractsResponse>(path);
}
