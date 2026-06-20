import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, Loader2, X, Sparkles, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChatStore } from "@/store/useChatStore";
import { API_BASE } from "@/lib/config";

interface DashboardGeneratorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  token: string | null;
}

const STAGES = [
  { id: "intent", label: "Анализ запроса" },
  { id: "sql", label: "Написание SQL" },
  { id: "clickhouse", label: "Извлечение данных" },
  { id: "synthesis", label: "Аналитика" },
  { id: "viz", label: "Визуализация" },
];

export const DashboardGeneratorModal: React.FC<DashboardGeneratorModalProps> = ({ isOpen, onClose, onSuccess, token }) => {
  const [topic, setTopic] = useState("");
  const [status, setStatus] = useState<'IDLE' | 'GENERATING' | 'ERROR'>('IDLE');
  const [pipelineState, setPipelineState] = useState<any>(null);
  const [errorMessage, setErrorMessage] = useState("");

  // Опрос статуса пайплайна
  useEffect(() => {
    let interval: any;
    if (status === 'GENERATING') {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/v1/pipeline/status`, {
            headers: { "Authorization": `Bearer ${token}` }
          });
          if (res.ok) {
            const data = await res.json();
            setPipelineState(data);
          }
        } catch (e) {
          console.error(e);
        }
      }, 500);
    }
    return () => clearInterval(interval);
  }, [status, token]);

  // Сброс при закрытии
  useEffect(() => {
    if (!isOpen) {
      setTimeout(() => {
        setStatus('IDLE');
        setTopic("");
        setPipelineState(null);
        setErrorMessage("");
      }, 300);
    }
  }, [isOpen]);

  // Polling pipeline status
  useEffect(() => {
    let interval: any;
    if (status === 'GENERATING') {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/v1/pipeline/status`);
          if (res.ok) {
            const data = await res.json();
            setPipelineState(data);
          }
        } catch (e) {
          // ignore
        }
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [status]);

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setStatus('GENERATING');
    setPipelineState(null);
    setErrorMessage("");
    try {
      const res = await fetch(`${API_BASE}/generate_dashboard`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}` 
        },
        body: JSON.stringify({
          question: topic,
          max_charts: 4,
          include_kpi: true
        })
      });
      
      if (!res.ok) throw new Error("Failed to generate dashboard");
      const data = await res.json();
      
      // Auto-pin and close immediately
      if (data?.charts && data.charts.length > 0) {
        const fullDashboard = {
          title: data.title || "Сгенерированный Дашборд",
          summary: data.summary || "ИИ-анализ на основе ваших данных.",
          insights: data.insights || [],
          recommendations: data.recommendations || [],
          reasoning: data.reasoning || "",
          kpi_cards: data.kpi_cards || [],
          charts: data.charts.map((chartSpec: any) => ({
            chart_type: chartSpec.chart_type,
            title: chartSpec.title,
            data: data.data
          }))
        };
        const newDashboard = {
          id: Date.now().toString(),
          title: fullDashboard.title,
          timestamp: Date.now(),
          data: JSON.stringify(fullDashboard)
        };
        useChatStore.getState().addDashboard(newDashboard);
        if (onSuccess) onSuccess();
        onClose();
      } else {
        setErrorMessage("Агенты не смогли сгенерировать графики для этого запроса. Попробуйте уточнить данные.");
        setStatus('ERROR');
      }
    } catch (e) {
      console.error(e);
      setErrorMessage("Произошла системная ошибка при генерации дашборда.");
      setStatus('ERROR');
    }
  };

  const isWide = false;

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            exit={{ opacity: 0 }} 
            className="absolute inset-0 bg-slate-950/80 backdrop-blur-md"
            onClick={() => status !== 'GENERATING' && onClose()}
          />
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: 20 }} 
            animate={{ opacity: 1, scale: 1, y: 0, width: isWide ? '100%' : '100%', maxWidth: isWide ? '64rem' : '32rem' }} 
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="relative bg-slate-900 border border-slate-700 shadow-[0_0_50px_rgba(0,0,0,0.5)] rounded-2xl overflow-hidden z-10 flex flex-col max-h-[90vh]"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-slate-800 shrink-0 bg-slate-900/80 backdrop-blur-xl z-20">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 flex items-center justify-center text-cyan-400 border border-cyan-500/20 shadow-[0_0_15px_rgba(34,211,238,0.1)]">
                  <LayoutDashboard className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white tracking-wide">
                    {status === 'IDLE' && 'Генерация Дашборда (AI)'}
                    {status === 'GENERATING' && 'Работа ИИ-Агентов...'}
                    {status === 'ERROR' && 'Ошибка генерации'}
                  </h2>
                  <p className="text-xs text-slate-400">
                    {status === 'IDLE' && 'Автоматическое создание набора графиков по теме'}
                    {status === 'GENERATING' && 'Ожидайте, агенты готовят данные и визуализации'}
                    {status === 'ERROR' && 'Что-то пошло не так'}
                  </p>
                </div>
              </div>
              {status !== 'GENERATING' && (
                <Button variant="ghost" size="icon" onClick={onClose} className="text-slate-400 hover:text-white rounded-full hover:bg-slate-800 transition-colors">
                  <X className="w-5 h-5" />
                </Button>
              )}
            </div>
            
            {/* Body */}
            <div className="overflow-y-auto custom-scrollbar flex-1">
              
              {/* IDLE STATE */}
              {status === 'IDLE' && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-8 space-y-6">
                  <div className="space-y-3">
                    <label className="text-sm font-medium text-slate-300">Тема или вопрос для дашборда</label>
                    <div className="relative group">
                      <div className="absolute -inset-0.5 bg-gradient-to-r from-primary to-cyan-500 rounded-lg blur opacity-20 group-focus-within:opacity-50 transition duration-500"></div>
                      <Input 
                        value={topic}
                        onChange={(e) => setTopic(e.target.value)}
                        placeholder="Например: Сравнительный анализ задолженности по регионам за 2024 год"
                        className="relative bg-slate-900 border-slate-700 text-white placeholder:text-slate-600 h-12 text-base focus-visible:ring-1 focus-visible:ring-primary shadow-inner"
                        onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
                      />
                    </div>
                    <p className="text-xs text-slate-500 pt-2 leading-relaxed">
                      Система проанализирует запрос, извлечет необходимые данные из DWH, проведет статистический анализ и сгенерирует до 4 интерактивных виджетов.
                    </p>
                  </div>
                </motion.div>
              )}

              {/* GENERATING STATE */}
              {status === 'GENERATING' && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-8 space-y-8">
                  <div className="flex flex-col space-y-6">
                    {STAGES.map((stage, idx) => {
                      const isActive = pipelineState?.active_stages?.includes(stage.id);
                      const stObj = pipelineState?.stages?.[stage.id];
                      const isDone = stObj?.status === "done";
                      const isError = stObj?.status === "error";

                      return (
                        <div key={stage.id} className="flex gap-4 relative">
                          {idx !== STAGES.length - 1 && (
                            <div className={`absolute left-4 top-10 bottom-[-24px] w-0.5 ${isDone ? 'bg-primary/50' : 'bg-slate-800'}`} />
                          )}
                          <div className={`relative z-10 w-8 h-8 rounded-full flex items-center justify-center shrink-0 border-2 transition-colors duration-500 ${isActive ? 'bg-primary/20 border-primary shadow-[0_0_15px_rgba(var(--primary),0.5)]' : isDone ? 'bg-emerald-500/20 border-emerald-500' : isError ? 'bg-rose-500/20 border-rose-500' : 'bg-slate-800 border-slate-700'}`}>
                            {isActive ? <Loader2 className="w-4 h-4 text-primary animate-spin" /> : 
                             isDone ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : 
                             isError ? <X className="w-4 h-4 text-rose-400" /> : 
                             <span className="text-xs text-slate-500 font-medium">{idx + 1}</span>}
                          </div>
                          <div className="flex-1 pt-1.5 pb-2">
                            <h4 className={`text-sm font-medium transition-colors ${isActive ? 'text-primary drop-shadow-[0_0_8px_rgba(var(--primary),0.8)]' : isDone ? 'text-emerald-400' : isError ? 'text-rose-400' : 'text-slate-500'}`}>
                              {stage.label}
                            </h4>
                            <AnimatePresence>
                              {(isActive || (isDone && stObj?.log)) && (
                                <motion.p 
                                  initial={{ opacity: 0, height: 0 }} 
                                  animate={{ opacity: 1, height: 'auto' }}
                                  className="text-xs text-slate-400 mt-1.5 break-words bg-slate-900/50 p-2 rounded-md border border-white/5 font-mono"
                                >
                                  {stObj?.log || "В процессе..."}
                                </motion.p>
                              )}
                            </AnimatePresence>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}

              {status === 'ERROR' && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-8">
                  <div className="p-6 bg-rose-500/10 border border-rose-500/20 rounded-xl">
                    <h3 className="text-rose-400 font-medium mb-2">Генерация не удалась</h3>
                    <p className="text-slate-300 text-sm leading-relaxed">{errorMessage}</p>
                  </div>
                </motion.div>
              )}
            </div>

            {/* Footer Actions */}
            <div className="p-6 bg-slate-900/80 backdrop-blur-xl border-t border-slate-800 flex justify-end gap-3 shrink-0">
              {status === 'IDLE' && (
                <>
                  <Button variant="ghost" onClick={onClose} className="text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
                    Отмена
                  </Button>
                  <Button 
                    onClick={handleGenerate} 
                    disabled={!topic.trim()}
                    className="bg-primary hover:bg-primary/90 text-white shadow-[0_0_20px_rgba(var(--primary),0.4)] hover:shadow-[0_0_30px_rgba(var(--primary),0.6)] transition-all"
                  >
                    <Sparkles className="w-4 h-4 mr-2" />
                    Запустить AI
                  </Button>
                </>
              )}

              {status === 'GENERATING' && (
                <div className="flex w-full items-center justify-between text-sm text-slate-500">
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    Пожалуйста, не закрывайте окно
                  </div>
                </div>
              )}

              {status === 'ERROR' && (
                <>
                  <Button variant="ghost" onClick={onClose} className="text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
                    Закрыть
                  </Button>
                  <Button 
                    onClick={() => { setStatus('IDLE'); setErrorMessage(""); }}
                    className="bg-primary hover:bg-primary/90 text-white shadow-[0_0_20px_rgba(var(--primary),0.4)] hover:shadow-[0_0_30px_rgba(var(--primary),0.6)] transition-all"
                  >
                    Попробовать снова
                  </Button>
                </>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};