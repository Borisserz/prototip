import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import { TrendingUp, TrendingDown } from "lucide-react";

/** Лёгкий SVG-спарклайн без зависимостей (для карточек клиентов). */
export const Sparkline: React.FC<{
  data: number[];
  color?: string;
  className?: string;
  height?: number;
}> = ({ data, color = "#38bdf8", className, height = 36 }) => {
  if (!data || data.length === 0) return <div style={{ height }} className={className} />;
  const w = 120;
  const h = height;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const span = max - min || 1;
  const step = w / Math.max(data.length - 1, 1);
  const pts = data.map((v, i) => [i * step, h - ((v - min) / span) * (h - 4) - 2]);
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;
  const gid = React.useId();
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cn("w-full", className)} style={{ height }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
};

/** KPI-карточка с иконкой, значением и опциональным трендом/подписью. */
export const StatCard: React.FC<{
  icon: LucideIcon;
  label: string;
  value: React.ReactNode;
  hint?: string;
  trend?: number;
  accent?: string; // tailwind text color class, напр. "text-sky-400"
}> = ({ icon: Icon, label, value, hint, trend, accent = "text-sky-400" }) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-4 backdrop-blur-md"
  >
    <div className="flex items-center justify-between">
      <span className="text-xs uppercase tracking-wider text-slate-400">{label}</span>
      <Icon className={cn("h-4 w-4", accent)} />
    </div>
    <div className="mt-2 flex items-end gap-2">
      <span className="text-2xl font-bold text-white leading-none">{value}</span>
      {typeof trend === "number" && (
        <span
          className={cn(
            "mb-0.5 inline-flex items-center gap-0.5 text-xs font-medium",
            trend >= 0 ? "text-emerald-400" : "text-rose-400",
          )}
        >
          {trend >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {Math.abs(trend).toFixed(1)}%
        </span>
      )}
    </div>
    {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
  </motion.div>
);

/** Цветной статус-бейдж. */
export const StatusBadge: React.FC<{ active: boolean }> = ({ active }) => (
  <span
    className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
      active ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-600/30 text-slate-400",
    )}
  >
    <span className={cn("h-1.5 w-1.5 rounded-full", active ? "bg-emerald-400" : "bg-slate-500")} />
    {active ? "Активен" : "Отключён"}
  </span>
);

/** Прогресс-полоса (для success rate / uptime). */
export const Meter: React.FC<{ value: number; color?: string }> = ({ value, color = "bg-emerald-400" }) => (
  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-700/60">
    <div className={cn("h-full rounded-full", color)} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
  </div>
);
