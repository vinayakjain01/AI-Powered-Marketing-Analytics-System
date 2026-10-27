// Typed client for the FastAPI backend. All calls are same-origin under /api.

export type Row = Record<string, string | number | null>;

export type Filters = { brand: string; region: string; start: string; end: string };

export interface AdsKpis {
  spend: number; revenue: number; purchases: number; impressions: number; clicks: number;
  roas: number | null; roi: number | null; cpc: number | null; ctr: number | null; cpm: number | null;
}
export interface StoreKpis {
  net_sales: number; gross_sales: number; discounts: number; returns: number;
  orders: number; items_sold: number; aov: number | null;
}
export interface TraceStep {
  step: number; tool: string; args: Record<string, unknown>; ok: boolean; summary: string; ms: number;
}
export interface AskResponse {
  answer: string; sql: string | null; steps: number; stopped_reason: string;
  trace: TraceStep[]; columns: string[]; rows: (string | number | null)[][]; truncated: boolean;
}
export interface Health { status: string; agent_enabled: boolean; embeddings: string; model: string }
export interface TableInfo {
  name: string; description: string; synonyms: string[]; primary_key: string[];
  foreign_keys: { columns: string[]; ref_table: string; ref_columns: string[] }[];
  columns: { name: string; type: string; description: string }[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

function qs(f: Partial<Filters> & Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => { if (v !== undefined && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<Health>("/api/health"),
  filters: () => request<{ brands: string[]; regions: string[]; date_min: string; date_max: string }>("/api/filters"),
  kpis: (f: Filters) => request<{ ads: AdsKpis; store: StoreKpis }>(`/api/kpis${qs(f)}`),
  trend: (f: Filters, grain: string) =>
    request<{ ads: Row[]; store: Row[] }>(`/api/trend${qs({ ...f, grain })}`),
  breakdown: (f: Filters, by: string) => request<{ rows: Row[] }>(`/api/breakdown${qs({ ...f, by })}`),
  storeBreakdown: (f: Filters, by: string) =>
    request<{ rows: Row[] }>(`/api/store/breakdown${qs({ ...f, by })}`),
  campaigns: (f: Filters, metric: string, order: string, minSpend: number) =>
    request<{ rows: Row[] }>(`/api/campaigns${qs({ ...f, metric, order, min_spend: minSpend, limit: 10 })}`),
  tables: () => request<{ tables: TableInfo[] }>("/api/tables"),
  search: (q: string) => request<{ tables: { table: string; score: number; description: string }[] }>(
    `/api/search${qs({ q, top_k: 5 })}`),
  ask: (question: string) =>
    request<AskResponse>("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
    }),
};
