import React, { useMemo } from 'react';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceArea,
} from 'recharts';
import { motion } from 'framer-motion';
import { TrendingUp, Sparkles, X, Activity } from 'lucide-react';
import { formatCompactNumber } from '../../utils/formatters';
import type { ForecastResponse } from '../../utils/forecastApi';

interface ForecastPanelProps {
  forecast: ForecastResponse;
  onClose?: () => void;
}

interface ChartRow {
  label: string;
  history: number | null;
  forecast: number | null;
  band: [number, number] | null;
  lower: number | null;
  upper: number | null;
  isForecast: boolean;
}

/** Подпись метода прогноза для человека. */
const METHOD_LABELS: Record<string, string> = {
  linear: 'Линейный тренд',
  holt_winters: 'Holt-Winters (сезонность)',
  mean: 'Скользящее среднее',
  constant: 'Константа',
  auto: 'Авто',
};

const fmt = (v: any) =>
  typeof v === 'number' && isFinite(v) ? formatCompactNumber(v) : '—';

const ForecastTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || payload.length === 0) return null;
  const row: ChartRow = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/95 backdrop-blur-md px-4 py-3 shadow-2xl text-sm">
      <p className="text-slate-200 font-semibold mb-1">{label}</p>
      {row.isForecast ? (
        <>
          <p className="text-violet-300">Прогноз: <span className="font-bold">{fmt(row.forecast)}</span></p>
          <p className="text-slate-400 text-xs mt-1">
            Интервал: {fmt(row.lower)} … {fmt(row.upper)}
          </p>
        </>
      ) : (
        <p className="text-sky-300">Факт: <span className="font-bold">{fmt(row.history)}</span></p>
      )}
    </div>
  );
};

export const ForecastPanel: React.FC<ForecastPanelProps> = ({ forecast, onClose }) => {
  const { chartData, splitLabel } = useMemo(() => {
    const xKey = forecast.x;
    const yKey = forecast.y;
    const rows = forecast.data || [];

    const data: ChartRow[] = rows.map((r) => {
      const isF = Boolean(r.is_forecast);
      const val = Number(r[yKey]);
      const lower = r.lower != null ? Number(r.lower) : null;
      const upper = r.upper != null ? Number(r.upper) : null;
      return {
        label: String(r[xKey]),
        history: isF ? null : val,
        forecast: isF ? val : null,
        band: isF && lower != null && upper != null ? [lower, upper] : null,
        lower,
        upper,
        isForecast: isF,
      };
    });

    // Мостик: соединяем последнюю фактическую точку с линией прогноза и зоной ДИ,
    // чтобы кривая и заливка не имели визуального разрыва.
    let lastHistIdx = -1;
    for (let i = 0; i < data.length; i++) if (!data[i].isForecast) lastHistIdx = i;
    let splitLabel: string | null = null;
    if (lastHistIdx >= 0 && lastHistIdx < data.length - 1) {
      const h = data[lastHistIdx].history;
      data[lastHistIdx].forecast = h;
      data[lastHistIdx].band = h != null ? [h, h] : null;
      splitLabel = data[lastHistIdx].label;
    }

    return { chartData: data, splitLabel };
  }, [forecast]);

  const metrics = forecast.metrics || {};
  const growth = metrics.growth_pct;
  const r2 = metrics.r2 ?? metrics.r_squared;
  const lastForecast = forecast.forecast?.[forecast.forecast.length - 1];
  const firstForecastLabel = chartData.find((d) => d.isForecast)?.label;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="premium-glass rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-500/5 to-transparent p-6 relative overflow-hidden"
    >
      {/* Заголовок */}
      <div className="flex items-start justify-between gap-4 mb-5 relative z-10">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-violet-500/15 border border-violet-500/25 flex items-center justify-center shadow-inner">
            <TrendingUp className="w-5 h-5 text-violet-300" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-transparent bg-clip-text bg-gradient-to-r from-white to-violet-200">
              {forecast.title || 'Прогноз'}
            </h3>
            <div className="flex items-center gap-2 mt-0.5">
              <Sparkles className="w-3.5 h-3.5 text-violet-400" />
              <span className="text-xs text-slate-400 font-medium tracking-wide">
                {METHOD_LABELS[forecast.method] || forecast.method} · горизонт {forecast.horizon}
              </span>
            </div>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white hover:bg-white/10 rounded-lg p-1.5 transition-colors"
            title="Скрыть прогноз"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Метрики */}
      <div className="flex flex-wrap gap-3 mb-5 relative z-10">
        {growth != null && (
          <div className="px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-sm">
            <span className="text-slate-400">Прирост: </span>
            <span className={`font-bold ${growth >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {growth >= 0 ? '+' : ''}{Number(growth).toFixed(1)}%
            </span>
          </div>
        )}
        {r2 != null && (
          <div className="px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-sm">
            <span className="text-slate-400">Точность (R²): </span>
            <span className="font-bold text-sky-300">{Number(r2).toFixed(2)}</span>
          </div>
        )}
        {lastForecast && (
          <div className="px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-sm">
            <span className="text-slate-400">{lastForecast.period}: </span>
            <span className="font-bold text-violet-300">{fmt(lastForecast.value)}</span>
            <span className="text-slate-500 text-xs"> ({fmt(lastForecast.lower)}…{fmt(lastForecast.upper)})</span>
          </div>
        )}
      </div>

      {/* График: история (сплошная), прогноз (пунктир), ДИ (заливка-зона) */}
      <div className="h-[340px] w-full relative z-10">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 16, left: 4, bottom: 4 }}>
            <defs>
              <linearGradient id="ciBand" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.08} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff12" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#ffffff22" />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              stroke="#ffffff22"
              tickFormatter={(v) => formatCompactNumber(v)}
              width={56}
            />
            <Tooltip content={<ForecastTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
              formatter={(value) => <span className="text-slate-300">{value}</span>}
            />

            {/* Затенение прогнозной области по оси X */}
            {firstForecastLabel && (
              <ReferenceArea
                x1={splitLabel || firstForecastLabel}
                x2={chartData[chartData.length - 1]?.label}
                fill="#a78bfa"
                fillOpacity={0.05}
                ifOverflow="extendDomain"
              />
            )}

            {/* Доверительный интервал — отдельная зона [lower, upper] */}
            <Area
              type="monotone"
              dataKey="band"
              name="Доверительный интервал"
              stroke="none"
              fill="url(#ciBand)"
              connectNulls
              isAnimationActive={false}
              activeDot={false}
            />

            {/* Историческая (фактическая) линия — сплошная */}
            <Line
              type="monotone"
              dataKey="history"
              name="Факт"
              stroke="#38bdf8"
              strokeWidth={2.5}
              dot={{ r: 3, fill: '#38bdf8' }}
              connectNulls={false}
              isAnimationActive={false}
            />

            {/* Прогнозная линия — пунктир */}
            <Line
              type="monotone"
              dataKey="forecast"
              name="Прогноз"
              stroke="#a78bfa"
              strokeWidth={2.5}
              strokeDasharray="6 5"
              dot={{ r: 3, fill: '#a78bfa' }}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Нарратив (LLM-резюме) */}
      {forecast.narrative && (
        <div className="mt-5 flex items-start gap-3 relative z-10">
          <div className="p-2 rounded-lg bg-violet-500/10 text-violet-300 flex-shrink-0">
            <Activity className="w-4 h-4" />
          </div>
          <p className="text-sm text-slate-300 leading-relaxed">{forecast.narrative}</p>
        </div>
      )}
    </motion.div>
  );
};
