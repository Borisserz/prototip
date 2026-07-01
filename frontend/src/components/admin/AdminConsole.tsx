import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutGrid, Plus, RefreshCw, Building2, Users, Activity, Database,
  ArrowLeft, ChevronRight, Loader2, AlertTriangle, Boxes, ShieldCheck,
} from "lucide-react";
import { MonitoringConsole } from "./MonitoringConsole";
import { RlsAdmin } from "./RlsAdmin";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, Tooltip as RTooltip, CartesianGrid,
} from "recharts";
import { Button } from "@/components/ui/button";
import { adminApi, fmt, type Overview, type OverviewClient } from "@/lib/adminApi";
import { Sparkline, StatCard, StatusBadge, Meter, ConsoleTabs } from "./widgets";
import { TenantDetail } from "./TenantDetail";
import { CreateTenantWizard } from "./CreateTenantWizard";

interface Props {
  onBack: () => void;
  onImpersonate: (token: string, name: string) => void;
}

/**
 * Админ-консоль «Мои блоки».
 * Лендинг показывает сводные KPI и сетку клиентских блоков; по клику —
 * детальная аналитика клиента; одной кнопкой — мастер создания нового блока.
 */
export const AdminConsole: React.FC<Props> = ({ onBack, onImpersonate }) => {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [tab, setTab] = useState<"blocks" | "monitoring" | "access">("blocks");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await adminApi.overview(30));
    } catch (e: any) {
      setError(e?.message || "Не удалось загрузить сводку");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  // Детальный экран клиента
  if (selected) {
    return (
      <TenantDetail
        clientId={selected}
        onBack={() => { setSelected(null); load(); }}
        onImpersonate={onImpersonate}
        onDeleted={() => { setSelected(null); load(); }}
      />
    );
  }

  // Страница «Мониторинг»
  if (tab === "monitoring") {
    return <MonitoringConsole onBack={onBack} onTabChange={(id) => setTab(id as "blocks" | "monitoring" | "access")} />;
  }

  // Страница «Доступ по ролям» (RLS)
  if (tab === "access") {
    return <RlsAdmin onBack={onBack} onTabChange={(id) => setTab(id as "blocks" | "monitoring" | "access")} />;
  }

  const s = overview?.summary;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar bg-slate-900/30 px-4 py-6 sm:px-8">
      {/* Заголовок */}
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={onBack} className="text-slate-400 hover:text-white">
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
                <LayoutGrid className="h-6 w-6 text-sky-400" /> Мои блоки
              </h1>
              <p className="text-sm text-slate-400">Клиенты, которым поставлен продукт — аналитика и управление</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ConsoleTabs
              current="blocks"
              onChange={(id) => setTab(id as "blocks" | "monitoring" | "access")}
              tabs={[
                { id: "blocks", label: "Мои блоки", icon: LayoutGrid },
                { id: "monitoring", label: "Мониторинг", icon: Activity },
                { id: "access", label: "Доступ", icon: ShieldCheck },
              ]}
            />
            <Button variant="ghost" onClick={load} className="text-slate-300" title="Обновить">
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
            <Button
              onClick={() => setWizardOpen(true)}
              className="bg-sky-500 text-white hover:bg-sky-600 shadow-lg shadow-sky-500/20"
            >
              <Plus className="mr-2 h-4 w-4" /> Создать новый блок
            </Button>
          </div>
        </div>

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
            <AlertTriangle className="h-4 w-4" /> {error}
          </div>
        )}

        {/* KPI-сводка */}
        <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard icon={Building2} label="Всего клиентов" value={s ? s.total_clients : "—"} accent="text-sky-400"
            hint={s ? `${s.active_clients} активных` : undefined} />
          <StatCard icon={Activity} label="Запросов / 30 дней" value={s ? fmt.compact(s.total_queries) : "—"} accent="text-violet-400" />
          <StatCard icon={Users} label="Пользователей" value={s ? fmt.num(s.total_users) : "—"} accent="text-emerald-400" />
          <StatCard icon={Boxes} label="Активных блоков" value={s ? s.active_clients : "—"} accent="text-amber-400" />
        </div>

        {/* График общей нагрузки */}
        {overview && overview.timeseries.length > 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="mt-4 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-300">Совокупная нагрузка по всем клиентам</h3>
              <span className="text-xs text-slate-500">последние 30 дней</span>
            </div>
            <div className="h-44 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={overview.timeseries} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="ovGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#33415533" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} tickFormatter={(d) => d.slice(5)} minTickGap={24} />
                  <RTooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: "#94a3b8" }} />
                  <Area type="monotone" dataKey="queries" name="Запросы" stroke="#38bdf8" strokeWidth={2} fill="url(#ovGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.div>
        )}

        {/* Сетка блоков */}
        <h2 className="mt-8 mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
          Блоки клиентов {overview ? `(${overview.clients.length})` : ""}
        </h2>

        {loading && !overview ? (
          <div className="flex items-center gap-2 py-12 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" /> Загрузка…
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <AnimatePresence>
              {overview?.clients.map((c) => (
                <ClientBlock key={c.client_id} c={c} onOpen={() => setSelected(c.client_id)} />
              ))}
            </AnimatePresence>

            {/* CTA-карточка создания */}
            <motion.button
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              onClick={() => setWizardOpen(true)}
              className="group flex min-h-[200px] flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-700 bg-slate-800/20 p-6 text-slate-400 transition-all hover:border-sky-500/50 hover:bg-sky-500/5 hover:text-sky-300"
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-slate-700 bg-slate-800/60 transition-colors group-hover:border-sky-500/40 group-hover:bg-sky-500/10">
                <Plus className="h-7 w-7" />
              </div>
              <span className="text-sm font-medium">Создать новый блок</span>
              <span className="text-xs text-slate-500">Для нового заказчика</span>
            </motion.button>
          </div>
        )}
      </div>

      <CreateTenantWizard
        isOpen={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onCreated={() => { setWizardOpen(false); load(); }}
      />
    </div>
  );
};

/** Карточка одного клиента с мини-статистикой. */
const ClientBlock: React.FC<{ c: OverviewClient; onOpen: () => void }> = ({ c, onOpen }) => (
  <motion.button
    layout
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0 }}
    onClick={onOpen}
    className="group flex flex-col rounded-xl border border-slate-700/50 bg-slate-800/40 p-5 text-left backdrop-blur-md transition-all hover:border-sky-500/40 hover:bg-slate-800/70 hover:shadow-lg hover:shadow-sky-500/5"
  >
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500/20 to-violet-500/20 text-sky-300 font-bold uppercase">
          {c.name?.slice(0, 1) || "?"}
        </div>
        <div className="min-w-0">
          <p className="truncate font-semibold text-white">{c.name}</p>
          <p className="truncate text-xs text-slate-500">{c.client_id}</p>
        </div>
      </div>
      <StatusBadge active={c.active} />
    </div>

    <div className="my-4">
      <Sparkline data={c.spark} color={c.trend_pct >= 0 ? "#34d399" : "#fb7185"} />
    </div>

    <div className="grid grid-cols-3 gap-2 text-center">
      <div>
        <p className="text-sm font-bold text-white">{fmt.compact(c.queries)}</p>
        <p className="text-[10px] uppercase text-slate-500">запросов</p>
      </div>
      <div>
        <p className="text-sm font-bold text-white">{c.users}</p>
        <p className="text-[10px] uppercase text-slate-500">юзеров</p>
      </div>
      <div>
        <p className="text-sm font-bold text-white">{fmt.pct(c.success_rate)}</p>
        <p className="text-[10px] uppercase text-slate-500">успех</p>
      </div>
    </div>

    <div className="mt-3">
      <Meter value={c.success_rate} color={c.success_rate >= 95 ? "bg-emerald-400" : "bg-amber-400"} />
    </div>

    <div className="mt-4 flex items-center justify-between border-t border-slate-700/40 pt-3">
      <span className="flex items-center gap-1 text-xs text-slate-500">
        <Database className="h-3 w-3" /> {c.config?.clickhouse?.database || "—"}
      </span>
      <span className="flex items-center gap-1 text-xs font-medium text-sky-400 group-hover:gap-2 transition-all">
        Открыть <ChevronRight className="h-3.5 w-3.5" />
      </span>
    </div>
  </motion.button>
);
