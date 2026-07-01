import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft, Activity, Users, Timer, CheckCircle2, Database, DollarSign,
  Cpu, HardDrive, LogIn, KeyRound, Trash2, Copy, Check, Loader2, RefreshCw,
  Settings2, ShieldAlert, Save, Radio, AlertTriangle, UserPlus, UserCog,
  LayoutDashboard, Presentation, X,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  adminApi, fmt, tenantUsersApi,
  type TenantStats, type TenantUserAccount, type TenantUsersResponse,
} from "@/lib/adminApi";
import { StatCard, StatusBadge, Meter } from "./widgets";
import { EtlPanel } from "./EtlPanel";

interface Props {
  clientId: string;
  onBack: () => void;
  onImpersonate: (token: string, name: string) => void;
  onDeleted: () => void;
}

const PIE_COLORS = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#fb7185", "#22d3ee"];
const CHART_TT = {
  contentStyle: { background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#94a3b8" },
};

/** детальная аналитика и управление одним клиентом. */
export const TenantDetail: React.FC<Props> = ({ clientId, onBack, onImpersonate, onDeleted }) => {
  const [data, setData] = useState<TenantStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"analytics" | "activity" | "users" | "etl" | "settings">("analytics");
  const [copied, setCopied] = useState<string | null>(null);
  const [tokens, setTokens] = useState<{ jwt: string; api: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // editable settings
  const [edit, setEdit] = useState({ name: "", allowed_tables: "", enforce_client_id: false, active: true });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await adminApi.stats(clientId, 30);
      setData(d);
      setEdit({
        name: d.client.name,
        allowed_tables: (d.client.allowed_tables || []).join(", "),
        enforce_client_id: d.client.enforce_client_id,
        active: d.client.active,
      });
    } catch (e: any) {
      setError(e?.message || "Ошибка загрузки статистики");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load();   }, [clientId]);

  const copy = (text: string, key: string) => {
    navigator.clipboard?.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  const doImpersonate = async () => {
    setBusy(true);
    try {
      const r = await adminApi.impersonate(clientId);
      onImpersonate(r.access_token, r.name);
    } catch (e: any) {
      setError(e?.message || "Не удалось войти как заказчик");
    } finally { setBusy(false); }
  };

  const doRotate = async () => {
    setBusy(true);
    try {
      const r = await adminApi.rotate(clientId);
      setTokens({ jwt: r.jwt_token, api: r.api_key });
    } catch (e: any) { setError(e?.message || "Ошибка ротации"); }
    finally { setBusy(false); }
  };

  const doSave = async () => {
    setBusy(true);
    try {
      await adminApi.update(clientId, {
        name: edit.name,
        allowed_tables: edit.allowed_tables.split(",").map((s) => s.trim()).filter(Boolean),
        enforce_client_id: edit.enforce_client_id,
        active: edit.active,
      });
      await load();
    } catch (e: any) { setError(e?.message || "Ошибка сохранения"); }
    finally { setBusy(false); }
  };

  const doDelete = async () => {
    if (!confirm(`Удалить клиента «${data?.client.name}»? Действие необратимо.`)) return;
    setBusy(true);
    try { await adminApi.remove(clientId); onDeleted(); }
    catch (e: any) { setError(e?.message || "Ошибка удаления"); setBusy(false); }
  };

  if (loading && !data) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-900/30 text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загрузка аналитики…
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-slate-900/30 text-rose-300">
        <AlertTriangle className="h-6 w-6" /> {error || "Нет данных"}
        <Button variant="outline" onClick={onBack}>Назад</Button>
      </div>
    );
  }

  const s = data.summary;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar bg-slate-900/30 px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Шапка */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={onBack} className="text-slate-400 hover:text-white">
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500/20 to-violet-500/20 text-lg font-bold uppercase text-sky-300">
              {data.client.name?.slice(0, 1)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-white">{data.client.name}</h1>
                <StatusBadge active={data.client.active} />
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${data.source === "live" ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-600/30 text-slate-400"}`}>
                  <Radio className="h-3 w-3" /> {data.source === "live" ? "Live-данные" : "Демо-данные"}
                </span>
              </div>
              <p className="text-sm text-slate-500">
                {data.client.client_id} · {data.client.clickhouse.host}:{data.client.clickhouse.port}/{data.client.clickhouse.database}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" onClick={load} className="text-slate-300" title="Обновить">
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
            <Button onClick={doImpersonate} disabled={busy} className="bg-violet-500 text-white hover:bg-violet-600">
              <LogIn className="mr-2 h-4 w-4" /> Войти как заказчик
            </Button>
          </div>
        </div>

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
            <AlertTriangle className="h-4 w-4" /> {error}
          </div>
        )}

        {/* Табы */}
        <div className="mt-6 flex gap-1 rounded-lg border border-slate-700/50 bg-slate-800/40 p-1 w-fit">
          {([["analytics", "Аналитика"], ["activity", "Активность"], ["users", "Пользователи"], ["etl", "Данные / ETL"], ["settings", "Настройки"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${tab === k ? "bg-sky-500/20 text-sky-300" : "text-slate-400 hover:text-white"}`}>
              {label}
            </button>
          ))}
        </div>

        {/* АНАЛИТИКА */}
        {tab === "analytics" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6 space-y-6">
            {/* KPI */}
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard icon={Activity} label="Запросов / 30д" value={fmt.compact(s.total_queries)} trend={s.trend_pct} accent="text-sky-400" />
              <StatCard icon={Users} label="Польз." value={s.active_users} accent="text-emerald-400" />
              <StatCard icon={Timer} label="Ср. латентность" value={fmt.ms(s.avg_latency_ms)} accent="text-amber-400" />
              <StatCard icon={CheckCircle2} label="Успешность" value={fmt.pct(s.success_rate)} accent="text-emerald-400" />
              <StatCard icon={HardDrive} label="Объём данных" value={`${s.data_volume_gb ?? 0} ГБ`} accent="text-violet-400" />
              <StatCard icon={Cpu} label="Токенов LLM" value={fmt.compact(s.tokens_total ?? 0)} accent="text-cyan-400" />
              <StatCard icon={DollarSign} label="Стоимость / мес" value={fmt.money(s.monthly_cost_usd ?? 0)} accent="text-emerald-400" />
              <StatCard icon={Database} label="Таблиц" value={s.tables_count ?? 0} accent="text-sky-400" />
            </div>

            {/* Запросы по времени + латентность */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Запросы по дням">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data.timeseries} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="qGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} tickFormatter={(d) => d.slice(5)} minTickGap={24} />
                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                    <RTooltip {...CHART_TT} />
                    <Area type="monotone" dataKey="queries" name="Запросы" stroke="#38bdf8" strokeWidth={2} fill="url(#qGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Латентность по дням (мс)">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.timeseries} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} tickFormatter={(d) => d.slice(5)} minTickGap={24} />
                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                    <RTooltip {...CHART_TT} />
                    <Line type="monotone" dataKey="latency_ms" name="мс" stroke="#fbbf24" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            {/* Типы запросов + топ таблиц */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Типы SQL-запросов">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={data.query_types} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={75} paddingAngle={2}>
                      {data.query_types.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <RTooltip {...CHART_TT} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Самые запрашиваемые таблицы">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.top_tables} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10, fill: "#64748b" }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} width={90} />
                    <RTooltip {...CHART_TT} />
                    <Bar dataKey="queries" name="Запросы" fill="#a78bfa" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            {/* Использование агентов */}
            <ChartCard title="Загрузка агентов (LangGraph)" height={220}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.agents} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                  <XAxis dataKey="agent" tick={{ fontSize: 10, fill: "#64748b" }} angle={-15} textAnchor="end" height={50} interval={0} />
                  <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                  <RTooltip {...CHART_TT} />
                  <Bar dataKey="calls" name="Вызовы" fill="#34d399" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Пользователи */}
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-4">
              <h3 className="mb-3 text-sm font-medium text-slate-300">Активные пользователи</h3>
              <div className="space-y-2">
                {data.users.map((u, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="w-44 shrink-0 truncate text-sm text-slate-300">{u.name}</span>
                    <div className="flex-1"><Meter value={(u.queries / (data.users[0]?.queries || 1)) * 100} color="bg-sky-400" /></div>
                    <span className="w-16 shrink-0 text-right text-xs text-slate-400">{fmt.num(u.queries)}</span>
                    <span className="w-24 shrink-0 text-right text-xs text-slate-500">{u.last_active}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {/* АКТИВНОСТЬ */}
        {tab === "activity" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="mt-6 overflow-hidden rounded-xl border border-slate-700/50 bg-slate-800/40">
            <div className="table-wrapper overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/50 text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3">Пользователь</th>
                    <th className="px-4 py-3">SQL-запрос</th>
                    <th className="px-4 py-3 text-right">Время</th>
                    <th className="px-4 py-3 text-center">Статус</th>
                    <th className="px-4 py-3 text-right">Когда</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_queries.map((q, i) => (
                    <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/40">
                      <td className="px-4 py-2.5 text-slate-300 whitespace-nowrap">{q.user}</td>
                      <td className="px-4 py-2.5"><code className="text-xs text-slate-400">{q.query}</code></td>
                      <td className="px-4 py-2.5 text-right text-slate-400 whitespace-nowrap">{fmt.ms(q.duration_ms)}</td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={`rounded px-1.5 py-0.5 text-xs ${q.status === "ok" ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"}`}>
                          {q.status === "ok" ? "OK" : "Ошибка"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-500 whitespace-nowrap">{q.time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}

        {/* НАСТРОЙКИ */}
        {tab === "users" && <TenantUsersTab clientId={clientId} />}

        {tab === "etl" && (
          <EtlPanel clientId={clientId} client={data.client} onChanged={load} />
        )}

        {tab === "settings" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Конфигурация */}
            <div className="space-y-4 rounded-xl border border-slate-700/50 bg-slate-800/40 p-5">
              <h3 className="flex items-center gap-2 text-sm font-medium text-slate-200">
                <Settings2 className="h-4 w-4 text-sky-400" /> Конфигурация клиента
              </h3>
              <Field label="Название">
                <input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Разрешённые таблицы (через запятую)">
                <input value={edit.allowed_tables} onChange={(e) => setEdit({ ...edit, allowed_tables: e.target.value })} className={inputCls} placeholder="sales, orders, customers" />
              </Field>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={edit.enforce_client_id} onChange={(e) => setEdit({ ...edit, enforce_client_id: e.target.checked })} />
                <ShieldAlert className="h-4 w-4 text-amber-400" /> Жёсткая row-isolation (<code className="text-xs">WHERE client_id = …</code>)
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} />
                Клиент активен
              </label>
              <div className="flex justify-end">
                <Button onClick={doSave} disabled={busy} className="bg-sky-500/15 text-sky-200 border border-sky-500/30 hover:bg-sky-500/25">
                  {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />} Сохранить
                </Button>
              </div>
            </div>

            {/* Токены и опасная зона */}
            <div className="space-y-4">
              <div className="space-y-3 rounded-xl border border-slate-700/50 bg-slate-800/40 p-5">
                <h3 className="flex items-center gap-2 text-sm font-medium text-slate-200">
                  <KeyRound className="h-4 w-4 text-emerald-400" /> Доступы клиента
                </h3>
                <p className="text-xs text-slate-500">
                  Коллекция семантики: <code className="text-slate-400">{data.client.vector_collection}</code>
                </p>
                {tokens ? (
                  <div className="space-y-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3">
                    <p className="text-xs text-emerald-300">Новые токены (скопируйте — JWT показывается один раз):</p>
                    {([["JWT", tokens.jwt], ["API-ключ", tokens.api]] as const).map(([label, val]) => (
                      <div key={label} className="flex items-center gap-2">
                        <span className="w-16 text-xs text-slate-400">{label}</span>
                        <code className="flex-1 truncate rounded bg-slate-950/60 px-2 py-1 text-xs text-slate-200">{val}</code>
                        <Button size="sm" variant="ghost" onClick={() => copy(val, label)}>
                          {copied === label ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">Перевыпустите токены, если ключ скомпрометирован.</p>
                )}
                <Button variant="outline" onClick={doRotate} disabled={busy} className="border-slate-700 text-slate-300">
                  <KeyRound className="mr-2 h-4 w-4" /> Перевыпустить токены
                </Button>
              </div>

              <div className="space-y-3 rounded-xl border border-rose-500/30 bg-rose-500/5 p-5">
                <h3 className="text-sm font-medium text-rose-300">Опасная зона</h3>
                <p className="text-xs text-slate-500">Удаление клиента убирает его из реестра. Это необратимо.</p>
                <Button variant="destructive" onClick={doDelete} disabled={busy}>
                  <Trash2 className="mr-2 h-4 w-4" /> Удалить клиента
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

const inputCls =
  "w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none";

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <label className="block space-y-1">
    <span className="text-xs text-slate-400">{label}</span>
    {children}
  </label>
);

const ChartCard: React.FC<{ title: string; children: React.ReactNode; height?: number }> = ({ title, children, height = 200 }) => (
  <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-4">
    <h3 className="mb-2 text-sm font-medium text-slate-300">{title}</h3>
    <div style={{ height }} className="w-full">{children}</div>
  </div>
);

// Вкладка «Пользователи»: CRUD пользователей блока с гранулярными правами
const ROLE_OPTIONS = ["manager", "analyst", "viewer"];

type UserForm = {
  username: string;
  password: string;
  role: string;
  allowed_tables: string[];
  allowed_columns: string[];
  rls_region: string;
  can_dashboard: boolean;
  can_presentation: boolean;
};

const emptyForm = (): UserForm => ({
  username: "",
  password: "",
  role: "manager",
  allowed_tables: [],
  allowed_columns: [],
  rls_region: "",
  can_dashboard: true,
  can_presentation: true,
});

const TenantUsersTab: React.FC<{ clientId: string }> = ({ clientId }) => {
  const [data, setData] = useState<TenantUsersResponse | null>(null);
  const [tables, setTables] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<string | null>(null); // username при редактировании
  const [form, setForm] = useState<UserForm>(emptyForm());

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, t] = await Promise.all([
        tenantUsersApi.list(clientId),
        tenantUsersApi.tables(clientId).catch(() => ({ client_id: clientId, tables: {} })),
      ]);
      setData(u);
      setTables(t.tables || {});
    } catch (e: any) {
      setError(e?.message || "Ошибка загрузки пользователей");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load();   }, [clientId]);

  const tableNames = Object.keys(tables);
  // колонки, доступные для выбора = объединение колонок выбранных таблиц (или всех)
  const columnPool = Array.from(
    new Set(
      (form.allowed_tables.length ? form.allowed_tables : tableNames)
        .flatMap((t) => tables[t] || []),
    ),
  );

  const toggle = (arr: string[], v: string) =>
    arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setShowForm(true);
  };

  const openEdit = (u: TenantUserAccount) => {
    setEditing(u.username);
    setForm({
      username: u.username,
      password: "",
      role: u.role,
      allowed_tables: u.allowed_tables || [],
      allowed_columns: u.allowed_columns || [],
      rls_region: (u.rls_filters?.region || []).join(", "),
      can_dashboard: u.can_dashboard,
      can_presentation: u.can_presentation,
    });
    setShowForm(true);
  };

  const buildRls = (): Record<string, string[]> => {
    const vals = form.rls_region.split(",").map((s) => s.trim()).filter(Boolean);
    return vals.length ? { region: vals } : {};
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      if (editing) {
        await tenantUsersApi.update(clientId, editing, {
          role: form.role,
          allowed_tables: form.allowed_tables,
          allowed_columns: form.allowed_columns,
          rls_filters: buildRls(),
          can_dashboard: form.can_dashboard,
          can_presentation: form.can_presentation,
          ...(form.password ? { password: form.password } : {}),
        });
      } else {
        await tenantUsersApi.create(clientId, {
          username: form.username,
          password: form.password,
          role: form.role,
          allowed_tables: form.allowed_tables,
          allowed_columns: form.allowed_columns,
          rls_filters: buildRls(),
          can_dashboard: form.can_dashboard,
          can_presentation: form.can_presentation,
        });
      }
      setShowForm(false);
      await load();
    } catch (e: any) {
      setError(e?.message || "Ошибка сохранения пользователя");
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (u: TenantUserAccount) => {
    setBusy(true);
    try {
      await tenantUsersApi.update(clientId, u.username, { active: !u.active });
      await load();
    } catch (e: any) { setError(e?.message || "Ошибка"); }
    finally { setBusy(false); }
  };

  const remove = async (u: TenantUserAccount) => {
    if (!confirm(`Удалить пользователя «${u.username}»?`)) return;
    setBusy(true);
    try { await tenantUsersApi.remove(clientId, u.username); await load(); }
    catch (e: any) { setError(e?.message || "Ошибка удаления"); }
    finally { setBusy(false); }
  };

  const limitReached = !!data?.max_users && (data?.active_count ?? 0) >= (data?.max_users ?? 0);

  if (loading && !data) {
    return (
      <div className="mt-6 flex items-center justify-center py-16 text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загрузка пользователей…
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6 space-y-4">
      {/* Шапка: лимит + кнопка создания */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Users className="h-4 w-4 text-sky-400" />
          Активных: <span className="text-slate-200">{data?.active_count ?? 0}</span>
          {!!data?.max_users && (
            <span className="text-slate-500">/ лимит {data.max_users}</span>
          )}
          {limitReached && (
            <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">
              Лимит достигнут
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={load} className="text-slate-300" title="Обновить">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button onClick={openCreate} disabled={limitReached}
            className="bg-sky-500 text-white hover:bg-sky-600 disabled:opacity-50">
            <UserPlus className="mr-2 h-4 w-4" /> Добавить пользователя
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
          <AlertTriangle className="h-4 w-4" /> {error}
        </div>
      )}

      {/* Список пользователей */}
      {(!data || data.users.length === 0) ? (
        <div className="rounded-xl border border-dashed border-slate-700/60 bg-slate-800/30 py-12 text-center text-sm text-slate-500">
          В этом блоке пока нет пользователей. Нажмите «Добавить пользователя».
        </div>
      ) : (
        <div className="space-y-2">
          {data.users.map((u) => (
            <div key={u.username}
              className="flex flex-col gap-3 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <UserCog className="h-4 w-4 text-violet-300" />
                  <span className="font-medium text-slate-100">{u.username}</span>
                  <span className="rounded bg-slate-700/50 px-1.5 py-0.5 text-xs text-slate-300">{u.role}</span>
                  {!u.active && (
                    <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-xs text-rose-300">отключён</span>
                  )}
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                  <span className="inline-flex items-center gap-1 rounded bg-slate-900/50 px-1.5 py-0.5">
                    <Database className="h-3 w-3" />
                    {u.allowed_tables.length ? `${u.allowed_tables.length} табл.` : "все таблицы"}
                  </span>
                  <span className="inline-flex items-center gap-1 rounded bg-slate-900/50 px-1.5 py-0.5">
                    {u.allowed_columns.length ? `${u.allowed_columns.length} колонок` : "все колонки"}
                  </span>
                  {!!(u.rls_filters?.region?.length) && (
                    <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-300">
                      <ShieldAlert className="h-3 w-3" /> region: {u.rls_filters.region.join(", ")}
                    </span>
                  )}
                  <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ${u.can_dashboard ? "bg-emerald-500/10 text-emerald-300" : "bg-slate-900/50 text-slate-500 line-through"}`}>
                    <LayoutDashboard className="h-3 w-3" /> дашборды
                  </span>
                  <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ${u.can_presentation ? "bg-emerald-500/10 text-emerald-300" : "bg-slate-900/50 text-slate-500 line-through"}`}>
                    <Presentation className="h-3 w-3" /> презентации
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => toggleActive(u)} disabled={busy}
                  className="border-slate-700 text-slate-300">
                  {u.active ? "Отключить" : "Включить"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => openEdit(u)} disabled={busy}
                  className="border-slate-700 text-slate-300">
                  <Settings2 className="mr-1.5 h-3.5 w-3.5" /> Права
                </Button>
                <Button size="sm" variant="destructive" onClick={() => remove(u)} disabled={busy}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Модал создания/редактирования */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowForm(false)}>
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto custom-scrollbar rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
                {editing ? <UserCog className="h-5 w-5 text-violet-300" /> : <UserPlus className="h-5 w-5 text-sky-300" />}
                {editing ? `Права: ${editing}` : "Новый пользователь блока"}
              </h3>
              <Button size="icon" variant="ghost" onClick={() => setShowForm(false)} className="text-slate-400">
                <X className="h-5 w-5" />
              </Button>
            </div>

            <div className="space-y-4">
              {!editing && (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field label="Логин">
                    <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                      className={inputCls} placeholder="ivan" autoFocus />
                  </Field>
                  <Field label="Пароль">
                    <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                      className={inputCls} placeholder="минимум 4 символа" />
                  </Field>
                </div>
              )}
              {editing && (
                <Field label="Новый пароль (оставьте пустым, чтобы не менять)">
                  <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className={inputCls} placeholder="••••••" />
                </Field>
              )}

              <Field label="Роль">
                <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className={inputCls}>
                  {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </Field>

              {/* Таблицы */}
              <div className="space-y-1">
                <span className="text-xs text-slate-400">
                  Разрешённые таблицы {form.allowed_tables.length === 0 && <em className="text-slate-500">(пусто = все таблицы блока)</em>}
                </span>
                {tableNames.length === 0 ? (
                  <p className="text-xs text-slate-500">Схема клиента недоступна. Можно указать вручную ниже.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {tableNames.map((t) => (
                      <button key={t} type="button"
                        onClick={() => setForm({ ...form, allowed_tables: toggle(form.allowed_tables, t), allowed_columns: [] })}
                        className={`rounded-md px-2 py-1 text-xs transition-colors ${form.allowed_tables.includes(t) ? "bg-sky-500/20 text-sky-200 border border-sky-500/40" : "bg-slate-800 text-slate-400 border border-slate-700 hover:text-white"}`}>
                        {t}
                      </button>
                    ))}
                  </div>
                )}
                <input value={form.allowed_tables.join(", ")}
                  onChange={(e) => setForm({ ...form, allowed_tables: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                  className={`${inputCls} mt-1`} placeholder="или через запятую: sales, orders" />
              </div>

              {/* Колонки */}
              <div className="space-y-1">
                <span className="text-xs text-slate-400">
                  Разрешённые колонки {form.allowed_columns.length === 0 && <em className="text-slate-500">(пусто = все колонки)</em>}
                </span>
                {columnPool.length > 0 && (
                  <div className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto custom-scrollbar rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                    {columnPool.map((c) => (
                      <button key={c} type="button"
                        onClick={() => setForm({ ...form, allowed_columns: toggle(form.allowed_columns, c) })}
                        className={`rounded-md px-2 py-1 text-xs transition-colors ${form.allowed_columns.includes(c) ? "bg-violet-500/20 text-violet-200 border border-violet-500/40" : "bg-slate-800 text-slate-400 border border-slate-700 hover:text-white"}`}>
                        {c}
                      </button>
                    ))}
                  </div>
                )}
                <input value={form.allowed_columns.join(", ")}
                  onChange={(e) => setForm({ ...form, allowed_columns: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                  className={`${inputCls} mt-1`} placeholder="или через запятую: region, paid, debt" />
              </div>

              {/* RLS */}
              <Field label="RLS-фильтр по region (через запятую — построчная изоляция)">
                <input value={form.rls_region} onChange={(e) => setForm({ ...form, rls_region: e.target.value })}
                  className={inputCls} placeholder="Гродненская область, г. Гродно" />
              </Field>

              {/* Фичи */}
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input type="checkbox" checked={form.can_dashboard} onChange={(e) => setForm({ ...form, can_dashboard: e.target.checked })} />
                  <LayoutDashboard className="h-4 w-4 text-sky-400" /> Генерация дашбордов
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input type="checkbox" checked={form.can_presentation} onChange={(e) => setForm({ ...form, can_presentation: e.target.checked })} />
                  <Presentation className="h-4 w-4 text-violet-400" /> Генерация презентаций
                </label>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setShowForm(false)} className="text-slate-400">Отмена</Button>
              <Button onClick={save} disabled={busy} className="bg-sky-500 text-white hover:bg-sky-600">
                {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                {editing ? "Сохранить права" : "Создать"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
};
