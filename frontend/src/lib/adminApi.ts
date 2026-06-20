/**
 * Phase 6 — типизированный клиент админ-консоли (multi-tenant B2B).
 *
 * Все запросы идут на FastAPI-бэкенд. Базовый URL вынесен сюда, чтобы не
 * дублировать `http://localhost:8000` по компонентам.
 */

export const API_BASE = "http://localhost:8000";

// ─── Типы конфигурации клиента ──────────────────────────────────────────────
export interface TenantConfig {
  client_id: string;
  name: string;
  clickhouse: { host: string; port: number; database: string; user: string };
  vector_collection: string;
  allowed_tables: string[];
  enforce_client_id: boolean;
  client_id_value?: string;
  active: boolean;
  created_at: string;
}

// ─── Типы статистики ─────────────────────────────────────────────────────────
export interface TenantSummary {
  total_queries: number;
  trend_pct?: number;
  active_users: number;
  avg_latency_ms: number;
  success_rate: number;
  error_count: number;
  data_volume_gb?: number;
  tables_count?: number;
  tokens_total?: number;
  monthly_cost_usd?: number;
  uptime_pct?: number;
  last_active?: string;
}

export interface TimePoint { date: string; queries: number; latency_ms?: number }
export interface NamedValue { name: string; value: number }
export interface TableUsage { name: string; queries: number }
export interface AgentUsage { agent: string; calls: number }
export interface TenantUser { name: string; queries: number; last_active: string }
export interface RecentQuery {
  user: string;
  query: string;
  duration_ms: number;
  status: "ok" | "error";
  time: string;
}

export interface TenantStats {
  source: "live" | "demo";
  client: TenantConfig;
  summary: TenantSummary;
  timeseries: TimePoint[];
  query_types: NamedValue[];
  top_tables: TableUsage[];
  agents: AgentUsage[];
  users: TenantUser[];
  recent_queries: RecentQuery[];
}

export interface OverviewClient {
  client_id: string;
  name: string;
  active: boolean;
  queries: number;
  users: number;
  success_rate: number;
  trend_pct: number;
  last_active: string;
  spark: number[];
  config: TenantConfig;
}

export interface Overview {
  source: string;
  summary: {
    total_clients: number;
    active_clients: number;
    total_queries: number;
    total_users: number;
  };
  timeseries: { date: string; queries: number }[];
  clients: OverviewClient[];
}

export interface CreatedTenant extends TenantConfig {
  jwt_token: string;
  api_key: string;
}

// ─── Низкоуровневый помощник ───────────────────────────────────────────────
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    throw new Error(j.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Методы админ-API ──────────────────────────────────────────────────────
export const adminApi = {
  overview: (days = 30) => request<Overview>(`/api/v1/admin/overview?days=${days}`),

  listTenants: () =>
    request<{ tenants: TenantConfig[] }>(`/api/v1/admin/tenants`),

  getTenant: (id: string) =>
    request<TenantConfig>(`/api/v1/admin/tenants/${encodeURIComponent(id)}`),

  stats: (id: string, days = 30) =>
    request<TenantStats>(`/api/v1/admin/tenants/${encodeURIComponent(id)}/stats?days=${days}`),

  create: (body: Record<string, unknown>) =>
    request<CreatedTenant>(`/api/v1/admin/tenants`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  update: (id: string, body: Record<string, unknown>) =>
    request<TenantConfig>(`/api/v1/admin/tenants/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  impersonate: (id: string) =>
    request<{ access_token: string; client_id: string; name: string; tenant: TenantConfig }>(
      `/api/v1/admin/tenants/${encodeURIComponent(id)}/impersonate`,
    ),

  rotate: (id: string) =>
    request<{ client_id: string; jwt_token: string; api_key: string }>(
      `/api/v1/admin/tenants/${encodeURIComponent(id)}/rotate-token`,
      { method: "POST" },
    ),

  remove: (id: string) =>
    request<{ success: boolean }>(`/api/v1/admin/tenants/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  clientLogin: (body: { api_key?: string; token?: string }) =>
    request<{
      access_token: string;
      role: string;
      is_admin: boolean;
      client_id: string;
      username: string;
      tenant: TenantConfig;
    }>(`/api/v1/client/login`, { method: "POST", body: JSON.stringify(body) }),
};

// ─── Phase 8: системные метрики (страница «Мониторинг») ─────────────────────
export interface MetricsSummary {
  total_calls: number;
  errors: number;
  error_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  active_agents: number;
  rps: number;
  calls_per_min: number;
}

export interface MetricsPoint {
  time: string;
  calls: number;
  latency_ms: number;
  errors: number;
  tokens: number;
  rpm: number;
}

export interface MetricsAgent {
  agent: string;
  calls: number;
  avg_latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  tokens: number;
  errors: number;
  error_rate: number;
}

export interface MetricsModel {
  model: string;
  calls: number;
  tokens: number;
  avg_latency_ms: number;
}

export interface MetricsError {
  time: string;
  agent: string;
  model: string;
  error: string;
}

export interface SystemMetrics {
  source: "live" | "demo";
  window_hours: number;
  bucket_minutes: number;
  generated_at: string;
  summary: MetricsSummary;
  timeseries: MetricsPoint[];
  by_agent: MetricsAgent[];
  by_model: MetricsModel[];
  recent_errors: MetricsError[];
}

export const metricsApi = {
  get: (hours = 24) => request<SystemMetrics>(`/api/v1/admin/metrics?hours=${hours}`),
};

// ─── JWT helpers ─────────────────────────────────────────────────────────────
export interface JwtClaims {
  sub?: string;
  role?: string;
  client_id?: string;
  exp?: number;
}

/** Безопасно декодирует payload JWT (без проверки подписи — только для UI). */
export function decodeJwt(token: string | null): JwtClaims | null {
  if (!token) return null;
  try {
    const part = token.split(".")[1];
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const decoded = decodeURIComponent(
      Array.from(json)
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join(""),
    );
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

export function isAdminToken(token: string | null): boolean {
  return decodeJwt(token)?.role === "admin";
}

// ─── Форматтеры ──────────────────────────────────────────────────────────────
export const fmt = {
  num: (n: number) =>
    new Intl.NumberFormat("ru-RU").format(Math.round(n || 0)),
  compact: (n: number) =>
    new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 }).format(n || 0),
  pct: (n: number) => `${(n ?? 0).toFixed(1)}%`,
  ms: (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(2)} с` : `${Math.round(n)} мс`),
  money: (n: number) =>
    new Intl.NumberFormat("ru-RU", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n || 0),
};
