
import { motion } from 'framer-motion';
import { useChatStore } from '../../store/useChatStore';
import { Brain, Search, Route, Database, LineChart, ShieldCheck, Presentation, CheckCircle2, Activity } from 'lucide-react';
import { cn } from '../../lib/utils';

const STEPS = [
  { id: "Планировщик", icon: Brain, label: "Планировщик" },
  { id: "RAG Поиск", icon: Search, label: "RAG Контекст" },
  { id: "Маршрутизатор", icon: Route, label: "Маршрутизатор" },
  { id: "Data Agent (SQL)", icon: Database, label: "Агент Данных" },
  { id: "Аналитик", icon: LineChart, label: "Аналитик" },
  { id: "Критик (CDO)", icon: ShieldCheck, label: "Критик" },
  { id: "Презентация", icon: Presentation, label: "Презентация" },
];

export function AgentGraph() {
  const activeNode = useChatStore((state) => state.activeNode);
  const pipelineStages = useChatStore((state) => state.pipelineStages);

  if (!activeNode) return null;

  // Determine the index of the active node to show progress
  const activeIndex = STEPS.findIndex(s => s.id === activeNode);

  return (
    <div className="w-full mt-4 py-4 px-8 rounded-2xl bg-slate-900/40 border border-slate-700/50 backdrop-blur-md shadow-lg overflow-hidden">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 4, ease: "linear" }}
          >
            <Brain className="w-4 h-4 text-indigo-400" />
          </motion.div>
          Live LangGraph Activity
        </h4>
        <span className="text-xs font-mono text-teal-400 bg-teal-500/10 px-2 py-0.5 rounded border border-teal-500/20">
          Running
        </span>
      </div>

      <div className="relative">
        {/* Background Line */}
        <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-slate-800 -translate-y-1/2 z-0" />

        {/* Progress Line */}
        <motion.div
          className="absolute top-1/2 left-0 h-0.5 bg-gradient-to-r from-indigo-500 to-teal-400 -translate-y-1/2 z-0"
          initial={{ width: "0%" }}
          animate={{ width: activeIndex >= 0 ? `${(activeIndex / (STEPS.length - 1)) * 100}%` : "0%" }}
          transition={{ duration: 0.5, ease: "easeInOut" }}
        />

        <div className="relative z-10 flex justify-between items-center w-full">
          {STEPS.map((step, idx) => {
            const isActive = step.id === activeNode;
            const isPast = activeIndex > idx;
            const Icon = isPast ? CheckCircle2 : step.icon;

            return (
              <div key={step.id} className="flex flex-col items-center gap-2 group relative">
                <motion.div
                  className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center border-2 transition-colors duration-300",
                    isActive
                      ? "bg-slate-900 border-teal-400 shadow-[0_0_15px_rgba(45,212,191,0.5)]"
                      : isPast
                      ? "bg-indigo-900/50 border-indigo-400 text-indigo-300"
                      : "bg-slate-900 border-slate-700 text-slate-500"
                  )}
                  animate={
                    isActive
                      ? { scale: [1, 1.15, 1], borderColor: ["#2dd4bf", "#818cf8", "#2dd4bf"] }
                      : { scale: 1 }
                  }
                  transition={isActive ? { repeat: Infinity, duration: 2 } : {}}
                >
                  <Icon className={cn("w-4 h-4", isActive ? "text-teal-400" : "")} />
                </motion.div>
                
                <span className={cn(
                  "absolute -bottom-6 text-[10px] font-medium whitespace-nowrap px-2 py-0.5 rounded transition-all",
                  isActive ? "text-teal-300 bg-teal-500/10 border border-teal-500/20" : "text-slate-500"
                )}>
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="h-6" /> {/* Spacer for absolute labels */}
      
      {/* Pipeline Detailed Logs */}
      {Object.keys(pipelineStages).length > 0 && (
        <div className="mt-8 space-y-2 border-t border-slate-700/50 pt-4">
          <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <Activity className="w-3 h-3" /> Детальный лог конвейера
          </h5>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {Object.entries(pipelineStages).filter(([_, st]: [string, any]) => st.log).map(([id, st]: [string, any]) => (
              <div key={id} className="p-3 rounded bg-slate-900/50 border border-slate-700/30 text-xs text-slate-300">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-semibold text-white">{id}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase ${st.status === 'running' ? 'bg-indigo-500/20 text-indigo-300' : st.status === 'done' ? 'bg-teal-500/20 text-teal-300' : 'bg-rose-500/20 text-rose-300'}`}>
                    {st.status}
                  </span>
                </div>
                <p className="text-slate-400 font-mono mt-1">{st.log}</p>
                {st.error && <p className="text-rose-400 font-mono mt-1">{st.error}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
