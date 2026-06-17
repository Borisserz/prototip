import React, { useMemo, useState } from 'react';
import { useChatStore } from '../../store/useChatStore';
import { DashboardToolbar } from './DashboardToolbar';
import { DynamicChart } from '../chat/DynamicChart';
import { Lightbulb, Info, TrendingUp, TrendingDown, Minus, CheckCircle2, BrainCircuit } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { exportDashboardToPDF } from '../../utils/dashboardPdfExport';

interface AIDashboardViewProps {
  onBackToChat: () => void;
}

const KPICard = ({ name, value, unit, change, change_period }: any) => {
  const isPositive = change > 0;
  const isNegative = change < 0;
  return (
    <div className="premium-glass p-5 rounded-2xl border border-white/5 relative overflow-hidden group">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
      <p className="text-sm font-medium text-slate-400 mb-1 leading-snug line-clamp-2" title={name}>{name}</p>
      <div className="flex items-baseline gap-2 mt-2">
        <h4 className="text-3xl font-bold text-white tracking-tight">{value}</h4>
        {unit && <span className="text-sm text-slate-500 font-medium">{unit}</span>}
      </div>
      {change !== null && change !== undefined && (
        <div className={`flex items-center gap-1 mt-3 text-xs font-medium ${isPositive ? 'text-emerald-400' : isNegative ? 'text-rose-400' : 'text-slate-400'}`}>
          {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : isNegative ? <TrendingDown className="w-3.5 h-3.5" /> : <Minus className="w-3.5 h-3.5" />}
          <span>{Math.abs(change)}% {change_period || ''}</span>
        </div>
      )}
    </div>
  );
};

export const AIDashboardView: React.FC<AIDashboardViewProps> = ({ onBackToChat }) => {
  const dashboardHistory = useChatStore((state) => state.dashboardHistory);
  const activeDashboardId = useChatStore((state) => state.activeDashboardId);
  const deleteDashboard = useChatStore((state) => state.deleteDashboard);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const dashboardData = useMemo(() => {
    if (!activeDashboardId) return null;
    const activeDashboard = dashboardHistory.find(d => d.id === activeDashboardId);
    if (!activeDashboard) return null;
    try {
      const parsed = JSON.parse(activeDashboard.data);
      if (Array.isArray(parsed)) {
        return {
          title: "Сгенерированный Дашборд",
          summary: "",
          insights: [],
          recommendations: [],
          reasoning: "",
          kpi_cards: [],
          charts: parsed,
        };
      }
      return parsed;
    } catch (e) {
      console.error("Failed to parse dashboard", e);
      return null;
    }
  }, [dashboardHistory, activeDashboardId]);

  const handleClear = () => {
    setShowDeleteConfirm(true);
  };

  const confirmClear = () => {
    if (activeDashboardId) {
      deleteDashboard(activeDashboardId);
    }
    setShowDeleteConfirm(false);
    onBackToChat();
  };

  const handleExportDashboard = async () => {
    if (!dashboardData) return;
    try {
      await exportDashboardToPDF(dashboardData);
    } catch (e) {
      console.error('PDF export failed:', e);
    }
  };

  if (!dashboardData || dashboardData.charts.length === 0) {
    return (
      <div className="flex flex-col gap-6 w-full max-w-7xl mx-auto h-full pb-10">
        <DashboardToolbar hasCharts={false} onClear={handleClear} onBackToChat={onBackToChat} onExport={handleExportDashboard} />
        <div className="flex-1 flex items-center justify-center border border-dashed border-white/10 rounded-2xl bg-white/5">
          <p className="text-slate-400">Нет сгенерированных данных.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 w-full max-w-7xl mx-auto h-full pb-10">
      <DashboardToolbar 
        title={dashboardData.title}
        hasCharts={dashboardData.charts.length > 0}
        onClear={handleClear}
        onBackToChat={onBackToChat}
        onExport={handleExportDashboard}
      />

      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar rounded-xl">
        <div className="space-y-8 p-6 bg-[#0f172a] min-h-max border border-white/5 shadow-2xl">
          {/* Summary Section */}
        {dashboardData.summary && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="premium-glass p-6 rounded-2xl border border-primary/20 bg-primary/5">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-xl bg-primary/20 text-primary shadow-inner">
                <Info className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-2 tracking-wide">Резюме анализа</h3>
                <p className="text-slate-300 leading-relaxed text-[15px]">{dashboardData.summary}</p>
              </div>
            </div>
          </motion.div>
        )}

        {/* KPIs Section */}
        {dashboardData.kpi_cards?.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <h3 className="text-xs uppercase tracking-widest text-slate-500 font-bold mb-4 ml-1">Ключевые показатели</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {dashboardData.kpi_cards.map((kpi: any, idx: number) => (
                <KPICard key={idx} {...kpi} />
              ))}
            </div>
          </motion.div>
        )}

        {/* Recommendations Section */}
        {dashboardData.recommendations?.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
            <h3 className="text-xs uppercase tracking-widest text-emerald-500 font-bold mb-4 ml-1">Рекомендации ИИ</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {dashboardData.recommendations.map((rec: string, idx: number) => (
                <div key={idx} className="premium-glass p-5 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 relative overflow-hidden group hover:border-emerald-500/40 transition-colors">
                  <div className="absolute top-0 right-0 p-3 opacity-20 group-hover:opacity-40 transition-opacity">
                    <CheckCircle2 className="w-12 h-12 text-emerald-400" />
                  </div>
                  <div className="flex flex-col h-full relative z-10">
                    <div className="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold mb-3 shadow-inner">
                      {idx + 1}
                    </div>
                    <p className="text-sm text-slate-300 leading-relaxed font-medium">{rec}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Main Content Layout */}
        <div className="flex flex-col xl:flex-row gap-6">
          {/* Charts Grid */}
          <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-6 items-start content-start">
            {dashboardData.charts.map((chartObj: any, idx: number) => {
              const jsonStr = JSON.stringify(chartObj);
              const isFullWidth = dashboardData.charts.length === 1 || (dashboardData.charts.length % 2 !== 0 && idx === dashboardData.charts.length - 1);
              return (
                <motion.div 
                  initial={{ opacity: 0, scale: 0.95 }} 
                  animate={{ opacity: 1, scale: 1 }} 
                  transition={{ delay: 0.2 + idx * 0.1 }}
                  key={idx} 
                  className={`h-[400px] premium-glass rounded-2xl border border-white/10 p-2 overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.12)] transition-transform duration-300 hover:-translate-y-1 ${isFullWidth ? 'md:col-span-2' : ''}`}
                >
                  <DynamicChart content={jsonStr} isPinnedView={true} />
                </motion.div>
              );
            })}
          </div>

          {/* Insights Sidebar */}
          {dashboardData.insights?.length > 0 && (
            <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }} className="w-full xl:w-[320px] flex-shrink-0">
              <div className="premium-glass p-5 rounded-2xl border border-white/5 sticky top-0 bg-slate-900/40 backdrop-blur-xl">
                <div className="flex items-center gap-2 mb-5">
                  <Lightbulb className="w-5 h-5 text-amber-400" />
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">Ключевые Инсайты</h3>
                </div>
                <div className="space-y-3">
                  {dashboardData.insights.map((insight: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-3 p-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] hover:border-white/10 transition-all duration-300">
                      <div className="w-6 h-6 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5 shadow-inner">
                        {idx + 1}
                      </div>
                      <p className="text-sm text-slate-300 leading-relaxed font-medium">{insight}</p>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </div>

        {/* Reasoning Footer */}
          {dashboardData.reasoning && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }} className="mt-8 pt-6 border-t border-white/5">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-slate-800/80 text-slate-400">
                  <BrainCircuit className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-slate-400 mb-1">Методология ИИ (Reasoning)</h4>
                  <p className="text-xs text-slate-500 leading-relaxed max-w-4xl">{dashboardData.reasoning}</p>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" 
              onClick={() => setShowDeleteConfirm(false)} 
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 10 }} 
              animate={{ opacity: 1, scale: 1, y: 0 }} 
              exit={{ opacity: 0, scale: 0.95, y: 10 }} 
              className="relative bg-slate-900 border border-slate-700/50 rounded-2xl p-6 shadow-2xl max-w-md w-full"
            >
              <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 rounded-full bg-rose-500/10 flex items-center justify-center text-rose-500 flex-shrink-0">
                  <Minus className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-200">Удалить дашборд?</h3>
                  <p className="text-sm text-slate-400 mt-1">
                    Вы уверены, что хотите удалить сгенерированный дашборд? Это действие нельзя отменить.
                  </p>
                </div>
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button 
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
                >
                  Отмена
                </button>
                <button 
                  onClick={confirmClear}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-rose-500 hover:bg-rose-600 transition-colors shadow-lg shadow-rose-500/20"
                >
                  Да, удалить
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
