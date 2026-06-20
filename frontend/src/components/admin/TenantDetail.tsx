import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft, Activity, Users, Timer, CheckCircle2, Database, DollarSign,
  Cpu, HardDrive, LogIn, KeyRound, Trash2, Copy, Check, Loader2, RefreshCw,
  Settings2, ShieldAlert, Save, Radio, AlertTriangle,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend,
} from "recharts";
import { Button } from "@/components/ui/button";
import { adminApi, fmt, type TenantStats } from "@/lib/adminApi";
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

/** Phase 6 — детальная аналитика и управление одним клиентом. */
export const TenantDetail: React.FC<Props> = ({ clientId, onBack, onImpersonate, onDeleted }) => {
  const [data, setData] = useState<TenantStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"analytics" | "activity" | "etl" | "settings">("analytics");
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
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [clientId]);

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
          {([["analytics", "Аналитика"], ["activity", "Активность"], ["etl", "Данные / ETL"], ["settings", "Настройки"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${tab === k ? "bg-sky-500/20 text-sky-300" : "text-slate-400 hover:text-white"}`}>
              {label}
            </button>
          ))}
        </div>

        {/* ── АНАЛИТИКА ─────────────────────────────────────────────────────── */}
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

        {/* ── АКТИВНОСТЬ ─────────────────────────────────────────────────────── */}
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

        {/* ── НАСТРОЙКИ ──────────────────────────────────────────────────────── */}
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
