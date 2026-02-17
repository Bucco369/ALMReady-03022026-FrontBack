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

/**
 * XHR-based multipart POST with two-phase progress hooks.
 * onProgress(0→80): fires as bytes are sent over the wire.
 * onBytesSent():    fires via upload.onloadend when ALL bytes are sent
 *                   (before the server responds). Use this to start a
 *                   simulated "backend processing" phase (80→98%).
 */
function xhrUpload<T>(
  path: string,
  formData: FormData,
  onProgress?: (pct: number) => void,
  onBytesSent?: () => void
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 80));
        }
      };
    }

    // onloadend fires when all bytes are sent, regardless of whether
    // progress events were emitted (handles tiny files too).
    if (onBytesSent) {
      xhr.upload.onloadend = onBytesSent;
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch {
          reject(new Error(`Failed to parse JSON response from ${path}`));
        }
      } else {
        reject(new Error(`HTTP ${xhr.status} ${xhr.statusText} on ${path}: ${xhr.responseText}`));
      }
    };

    xhr.onerror = () => reject(new Error(`Network error on ${path}`));
    xhr.send(formData);
  });
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

export type CalculateRequest = {
  discount_curve_id?: string;
  scenarios?: string[];
  analysis_date?: string;
  currency?: string;
  risk_free_index?: string;
};

export type ScenarioResultItem = {
  scenario_id: string;
  scenario_name: string;
  eve: number;
  nii: number;
  delta_eve: number;
  delta_nii: number;
};

export type CalculationResultsResponse = {
  session_id: string;
  base_eve: number;
  base_nii: number;
  worst_case_eve: number;
  worst_case_delta_eve: number;
  worst_case_scenario: string;
  scenario_results: ScenarioResultItem[];
  calculated_at: string;
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

export async function uploadBalanceExcel(
  sessionId: string,
  file: File,
  onProgress?: (pct: number) => void,
  onBytesSent?: () => void
): Promise<BalanceSummaryResponse> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return xhrUpload<BalanceSummaryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/balance`,
    fd,
    onProgress,
    onBytesSent
  );
}

export async function uploadBalanceZip(
  sessionId: string,
  file: File,
  onProgress?: (pct: number) => void,
  onBytesSent?: () => void
): Promise<BalanceSummaryResponse> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return xhrUpload<BalanceSummaryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/balance/zip`,
    fd,
    onProgress,
    onBytesSent
  );
}

export async function getBalanceSummary(sessionId: string): Promise<BalanceSummaryResponse> {
  return http<BalanceSummaryResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/balance/summary`);
}

export async function uploadCurvesExcel(
  sessionId: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<CurvesSummaryResponse> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return xhrUpload<CurvesSummaryResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/curves`,
    fd,
    onProgress
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

export async function calculateEveNii(
  sessionId: string,
  request?: CalculateRequest,
): Promise<CalculationResultsResponse> {
  return http<CalculationResultsResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/calculate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request ?? {}),
    }
  );
}

export async function getCalculationResults(
  sessionId: string,
): Promise<CalculationResultsResponse> {
  return http<CalculationResultsResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/results`
  );
}
