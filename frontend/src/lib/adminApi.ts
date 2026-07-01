/** Типизированный HTTP-клиент для API админ-консоли. */

import { API_BASE } from "@/lib/config";
export { API_BASE };

// Типы конфигурации клиента
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
  // ETL-оркестрация
  pg_configured?: boolean;
  pg_schema?: string;
  etl_schedule?: string;
  etl_enabled?: boolean;
  max_users?: number;
  docs_collection?: string;
  last_etl_status?: string;
  last_etl_at?: string;
  last_etl_message?: string;
}

// типы ETL
export interface EtlStatus {
  client_id: string;
  status: string;            // idle | running | success | failed
  last_run_at?: string;
  message?: string;
  etl_enabled?: boolean;
  etl_schedule?: string;
  pg_configured?: boolean;
}

export interface EtlRun {
  dag_run_id: string;
  state: string;
  execution_date?: string;
  note?: string;
}

export interface TenantDoc {
  source: string;
  chunks: number;
}

// Типы статистики
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

// Низкоуровневый помощник
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Прокидываем JWT из localStorage в заголовок Authorization. Без этого админ-API
  // (require_admin) отвечает 401/403 на другом origin (frontend:5173 → backend:8000),
  // что раньше давало «Load failed» в «Мои блоки».
  const token = typeof localStorage !== "undefined" ? localStorage.getItem("jwt_token") : null;
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    throw new Error(j.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// Методы админ-API
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

// ETL-оркестрация (Airflow): кнопочная инициализация клиента
const T = (id: string) => `/api/v1/admin/tenants/${encodeURIComponent(id)}`;

export const etlApi = {
  /** Проверить подключение к Postgres ДО создания клиента (визард). */
  probeConnection: (pg_dsn: string, pg_schema = "public") =>
    request<{ ok: boolean; tables: string[]; count: number }>(
      `/api/v1/admin/etl/test-connection`,
      { method: "POST", body: JSON.stringify({ pg_dsn, pg_schema }) },
    ),

  /** Проверить read-only доступ к Postgres существующего клиента. */
  testConnection: (id: string, pg_dsn: string, pg_schema = "public") =>
    request<{ ok: boolean; tables: string[]; count: number }>(
      `${T(id)}/etl/test-connection`,
      { method: "POST", body: JSON.stringify({ pg_dsn, pg_schema }) },
    ),

  /** Инициализировать инстанс клиента одной кнопкой (PG → ETL). */
  provision: (id: string, body: Record<string, unknown> = {}) =>
    request<{ status: string; mode: string; dag_run_id?: string }>(
      `${T(id)}/provision`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  /** Запустить синхронизацию данных. */
  run: (id: string, body: Record<string, unknown> = {}) =>
    request<{ status: string; mode: string; dag_run_id?: string }>(
      `${T(id)}/etl/run`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  /** Текущий статус ETL клиента. */
  status: (id: string) => request<EtlStatus>(`${T(id)}/etl/status`),

  /** Последние запуски (Airflow или реестр). */
  runs: (id: string, limit = 10) =>
    request<{ source: string; runs: EtlRun[] }>(`${T(id)}/etl/runs?limit=${limit}`),

  /** Настроить cron-расписание и вкл/выкл автосинхронизацию. */
  setSchedule: (id: string, body: { etl_schedule?: string; etl_enabled?: boolean }) =>
    request<{ etl_schedule: string; etl_enabled: boolean; Airflow_synced: boolean; note: string }>(
      `${T(id)}/etl/schedule`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  /** Пересобрать только семантический слой. */
  rebuildSemantics: (id: string) =>
    request<{ status: string; task: string }>(`${T(id)}/semantics`, { method: "POST" }),

  /** Список документов в персональном RAG клиента. */
  listDocs: (id: string) =>
    request<{ collection: string; documents: TenantDoc[]; error?: string }>(`${T(id)}/docs`),

  /** Загрузить документ клиента в его RAG (multipart). */
  uploadDoc: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const token = typeof localStorage !== "undefined" ? localStorage.getItem("jwt_token") : null;
    const res = await fetch(`${API_BASE}${T(id)}/docs`, {
      method: "POST",
      body: fd,
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    return res.json() as Promise<{ status: string; filename: string; size: number; note: string }>;
  },
};

// системные метрики (страница «Мониторинг»)
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

// RLS: доступ по ролям (строчные фильтры), редактируется админом
export interface RlsRules {
  status: string;
  rules: Record<string, Record<string, string[]>>; // {role: {column: [values]}}
  roles: string[];
  regions: string[];
  column: string;
}

export const rlsApi = {
  /** Текущие правила + доступные роли и значения регионов. */
  get: () => request<RlsRules>(`/api/v1/admin/rls`),

  /** Задать значения фильтра для роли (напр. region IN (...)). */
  setRule: (role: string, values: string[], column = "region") =>
    request<{ status: string; role: string; column: string; values: string[] }>(
      `/api/v1/admin/rls/${encodeURIComponent(role)}`,
      { method: "PUT", body: JSON.stringify({ column, values }) },
    ),
};

// Per-tenant users: управление пользователями внутри блока (admin)
export interface TenantUserAccount {
  client_id: string;
  username: string;
  role: string;
  allowed_tables: string[];
  allowed_columns: string[];
  rls_filters: Record<string, string[]>;
  can_dashboard: boolean;
  can_presentation: boolean;
  active: boolean;
}

export interface TenantUsersResponse {
  client_id: string;
  users: TenantUserAccount[];
  max_users: number;
  active_count: number;
}

export interface TenantTablesResponse {
  client_id: string;
  tables: Record<string, string[]>; // {table: [columns]}
}

export interface TenantUserCreateBody {
  username: string;
  password: string;
  role?: string;
  allowed_tables?: string[];
  allowed_columns?: string[];
  rls_filters?: Record<string, string[]>;
  can_dashboard?: boolean;
  can_presentation?: boolean;
}

export type TenantUserUpdateBody = Partial<Omit<TenantUserCreateBody, "username">> & {
  active?: boolean;
};

const TU = (id: string) => `/api/v1/admin/tenants/${encodeURIComponent(id)}`;

export const tenantUsersApi = {
  /** Список пользователей блока + лимит max_users и число активных. */
  list: (id: string) => request<TenantUsersResponse>(`${TU(id)}/users`),

  /** Доступные таблицы и колонки клиента (для назначения прав). */
  tables: (id: string) => request<TenantTablesResponse>(`${TU(id)}/tables`),

  /** Создать пользователя блока. */
  create: (id: string, body: TenantUserCreateBody) =>
    request<TenantUserAccount>(`${TU(id)}/users`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Обновить пользователя блока (права, роль, RLS, пароль, статус). */
  update: (id: string, username: string, body: TenantUserUpdateBody) =>
    request<TenantUserAccount>(`${TU(id)}/users/${encodeURIComponent(username)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /** Удалить (мягко) пользователя блока. */
  remove: (id: string, username: string) =>
    request<{ success: boolean }>(`${TU(id)}/users/${encodeURIComponent(username)}`, {
      method: "DELETE",
    }),
};

// JWT helpers
export interface JwtClaims {
  sub?: string;
  role?: string;
  client_id?: string;
  exp?: number;
}

/** Безопасно декодирует полезная нагрузка JWT (без проверки подписи — только для UI). */
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

// Форматтеры
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
