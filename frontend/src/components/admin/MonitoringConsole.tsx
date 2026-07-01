import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity, ArrowLeft, RefreshCw, Gauge, Timer, AlertTriangle, Coins,
  Bot, Cpu, LayoutGrid, Loader2, Radio, Server,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend, Cell,
} from "recharts";
import { Button } from "@/components/ui/button";
import { metricsApi, fmt, type SystemMetrics } from "@/lib/adminApi";
import { StatCard, ConsoleTabs } from "./widgets";

interface Props {
  onBack: () => void;
  onTabChange: (id: string) => void;
}

const WINDOWS = [
  { id: 1, label: "1ч" },
  { id: 6, label: "6ч" },
  { id: 24, label: "24ч" },
  { id: 168, label: "7д" },
];

const AGENT_COLORS = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#fb7185", "#22d3ee", "#f472b6"];

const tooltipStyle = {
  background: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 8,
  fontSize: 12,
} as const;

/** Форматирует ISO-время в HH:MM (или DD.MM для широких окон). */
function fmtTime(iso: string, wide: boolean): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return wide
    ? `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`
    : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/**
 * страница «Мониторинг».
 * Нативный дашборд на recharts, читает живые агрегаты из /api/v1/admin/metrics.
 */
export const MonitoringConsole: React.FC<Props> = ({ onBack, onTabChange }) => {
  const [data, setData] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [auto, setAuto] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      setData(await metricsApi.get(hours));
    } catch (e: any) {
      setError(e?.message || "Не удалось загрузить метрики");
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => { load(); }, [load]);

  // Авто-обновление (живые метрики)
  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (auto) timer.current = setInterval(() => load(true), 15000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [auto, load]);

  const wide = hours > 24;
  const ts = (data?.timeseries || []).map((p) => ({ ...p, t: fmtTime(p.time, wide) }));
  const sum = data?.summary;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar bg-slate-900/30 px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Заголовок */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={onBack} className="text-slate-400 hover:text-white">
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
                <Activity className="h-6 w-6 text-sky-400" /> Мониторинг
              </h1>
              <p className="text-sm text-slate-400">Живые системные метрики платформы — LLM, агенты, токены</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <ConsoleTabs
              current="monitoring"
              onChange={onTabChange}
              tabs={[
                { id: "blocks", label: "Мои блоки", icon: LayoutGrid },
                { id: "monitoring", label: "Мониторинг", icon: Activity },
              ]}
            />
          </div>
        </div>

        {/* Панель управления */}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1 rounded-lg border border-slate-700/60 bg-slate-800/40 p-1">
            {WINDOWS.map((w) => (
              <button
                key={w.id}
                onClick={() => setHours(w.id)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  hours === w.id ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white"
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {data && (
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                  data.source === "live"
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "bg-amber-500/15 text-amber-300"
                }`}
                title={data.source === "live" ? "Реальные данные из ClickHouse" : "Демо-данные (нет трафика)"}
              >
                <Radio className="h-3 w-3" /> {data.source === "live" ? "LIVE" : "DEMO"}
              </span>
            )}
            <button
              onClick={() => setAuto((v) => !v)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                auto
                  ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
                  : "border-slate-700/60 bg-slate-800/40 text-slate-400 hover:text-white"
              }`}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${auto ? "animate-spin" : ""}`} /> Авто 15с
            </button>
            <Button variant="ghost" onClick={() => load()} className="text-slate-300" title="Обновить">
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
            <AlertTriangle className="h-4 w-4" /> {error}
          </div>
        )}

        {loading && !data ? (
          <div className="flex items-center gap-2 py-16 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" /> Загрузка метрик…
          </div>
        ) : (
          <>
            {/* KPI-сводка */}
            <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              <StatCard icon={Gauge} label="RPS" value={sum ? sum.rps.toFixed(3) : "—"} accent="text-sky-400"
                hint={sum ? `${fmt.num(sum.calls_per_min)} /мин` : undefined} />
              <StatCard icon={Timer} label="Латентность avg" value={sum ? fmt.ms(sum.avg_latency_ms) : "—"} accent="text-violet-400" />
              <StatCard icon={Timer} label="Латентность p95" value={sum ? fmt.ms(sum.p95_latency_ms) : "—"} accent="text-fuchsia-400" />
              <StatCard icon={AlertTriangle} label="Error-rate" value={sum ? fmt.pct(sum.error_rate) : "—"}
                accent={sum && sum.error_rate > 5 ? "text-rose-400" : "text-emerald-400"}
                hint={sum ? `${fmt.num(sum.errors)} ошибок` : undefined} />
              <StatCard icon={Coins} label="Токены" value={sum ? fmt.compact(sum.total_tokens) : "—"} accent="text-amber-400"
                hint={sum ? `${fmt.compact(sum.prompt_tokens)} in / ${fmt.compact(sum.completion_tokens)} out` : undefined} />
              <StatCard icon={Bot} label="Активных агентов" value={sum ? sum.active_agents : "—"} accent="text-emerald-400"
                hint={sum ? `${fmt.num(sum.total_calls)} вызовов` : undefined} />
            </div>

            {/* Графики: нагрузка + латентность */}
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Нагрузка (запросов/мин)" icon={Activity}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={ts} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                    <defs>
                      <linearGradient id="loadGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={24} />
                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} width={36} />
                    <RTooltip contentStyle={tooltipStyle} labelStyle={{ color: "#94a3b8" }} />
                    <Area type="monotone" dataKey="rpm" name="запр./мин" stroke="#38bdf8" strokeWidth={2} fill="url(#loadGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Латентность LLM (мс)" icon={Timer}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={ts} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={24} />
                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} width={36} />
                    <RTooltip contentStyle={tooltipStyle} labelStyle={{ color: "#94a3b8" }} />
                    <Line type="monotone" dataKey="latency_ms" name="латентность" stroke="#a78bfa" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            {/* Графики: ошибки + расход токенов */}
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Ошибки во времени" icon={AlertTriangle}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={ts} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={24} />
                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} width={36} allowDecimals={false} />
                    <RTooltip contentStyle={tooltipStyle} labelStyle={{ color: "#94a3b8" }} />
                    <Bar dataKey="errors" name="ошибки" fill="#fb7185" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Расход токенов" icon={Coins}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={ts} margin={{ top: 6, right: 10, left: -8, bottom: 0 }}>
                    <defs>
                      <linearGradient id="tokGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#fbbf24" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#fbbf24" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={24} />
                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} width={48}
                      tickFormatter={(v) => fmt.compact(v as number)} />
                    <RTooltip contentStyle={tooltipStyle} labelStyle={{ color: "#94a3b8" }}
                      formatter={(v: any) => fmt.num(v)} />
                    <Area type="monotone" dataKey="tokens" name="токены" stroke="#fbbf24" strokeWidth={2} fill="url(#tokGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            {/* Разбивка по агентам */}
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Вызовы по агентам" icon={Bot}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data?.by_agent || []} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10, fill: "#64748b" }} />
                    <YAxis type="category" dataKey="agent" tick={{ fontSize: 11, fill: "#94a3b8" }} width={90} />
                    <RTooltip contentStyle={tooltipStyle} labelStyle={{ color: "#94a3b8" }} cursor={{ fill: "#33415533" }} />
                    <Bar dataKey="calls" name="вызовы" radius={[0, 3, 3, 0]}>
                      {(data?.by_agent || []).map((_, i) => (
                        <Cell key={i} fill={AGENT_COLORS[i % AGENT_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Токены по агентам" icon={Cpu}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data?.by_agent || []} margin={{ top: 4, right: 10, left: -8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                    <XAxis dataKey="agent" tick={{ fontSize: 10, fill: "#64748b" }} interval={0} angle={-20} textAnchor="end" height={50} />
                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} width={48} tickFormatter={(v) => fmt.compact(v as number)} />
                    <RTooltip contentStyle={tooltipStyle} labelStyle={{ color: "#94a3b8" }} formatter={(v: any) => fmt.num(v)} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="prompt_tokens" name="prompt" stackId="a" fill="#38bdf8" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="completion_tokens" name="completion" stackId="a" fill="#a78bfa" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            {/* Таблица по агентам */}
            <div className="mt-4 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
                <Server className="h-4 w-4 text-sky-400" /> Сводка по агентам
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/50 text-xs uppercase tracking-wider text-slate-500">
                      <th className="px-2 py-2">Агент</th>
                      <th className="px-2 py-2 text-right">Вызовы</th>
                      <th className="px-2 py-2 text-right">Латентность avg</th>
                      <th className="px-2 py-2 text-right">Токены</th>
                      <th className="px-2 py-2 text-right">Error-rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.by_agent || []).map((a) => (
                      <tr key={a.agent} className="border-b border-slate-800/60 text-slate-300">
                        <td className="px-2 py-2 font-medium text-white">{a.agent}</td>
                        <td className="px-2 py-2 text-right">{fmt.num(a.calls)}</td>
                        <td className="px-2 py-2 text-right">{fmt.ms(a.avg_latency_ms)}</td>
                        <td className="px-2 py-2 text-right">{fmt.compact(a.tokens)}</td>
                        <td className={`px-2 py-2 text-right font-medium ${a.error_rate > 5 ? "text-rose-400" : "text-emerald-400"}`}>
                          {fmt.pct(a.error_rate)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Последние ошибки */}
            {data && data.recent_errors.length > 0 && (
              <div className="mt-4 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
                  <AlertTriangle className="h-4 w-4 text-rose-400" /> Последние ошибки
                </h3>
                <div className="space-y-2">
                  {data.recent_errors.map((e, i) => (
                    <div key={i} className="flex flex-col gap-1 rounded-lg border border-slate-700/40 bg-slate-900/40 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <span className="font-medium text-rose-300">{e.agent}</span>
                        <span className="ml-2 text-xs text-slate-500">{e.model}</span>
                        <p className="truncate text-xs text-slate-400">{e.error}</p>
                      </div>
                      <span className="shrink-0 text-xs text-slate-500">{fmtTime(e.time, wide)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="mt-6 text-center text-xs text-slate-600">
              Обновлено: {data ? new Date(data.generated_at).toLocaleString("ru-RU") : "—"}
              {data && ` · окно ${data.window_hours}ч · шаг ${data.bucket_minutes} мин`}
            </p>
          </>
        )}
      </div>
    </div>
  );
};

/** Карточка-обёртка для графика (единый стиль). */
const ChartCard: React.FC<{ title: string; icon: typeof Activity; children: React.ReactNode }> = ({
  title, icon: Icon, children,
}) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-4"
  >
    <h3 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-300">
      <Icon className="h-4 w-4 text-sky-400" /> {title}
    </h3>
    <div className="h-56 w-full">{children}</div>
  </motion.div>
);
