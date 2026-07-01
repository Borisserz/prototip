import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Sparkles, Presentation, Loader2, CheckCircle2, Circle,
  BrainCircuit, Database, BarChart3, FileSliders, Zap, ChevronRight,
  Plus, Trash2, GripVertical, Users, Target, Palette, Settings2,
  BarChart2, TrendingUp, PieChart, Activity, AlertCircle, Info,
  Lightbulb, ChevronDown, ChevronUp, Globe2
} from 'lucide-react';
import { Button } from '../ui/button';
import { useChatStore } from '../../store/useChatStore';
import { API_BASE } from "@/lib/config";

const API = API_BASE;
// Stage Config
interface Stage {
  id: string;
  label: string;
  icon: React.ReactNode;
  detail: string;
}

const STAGES: Stage[] = [
  { id: 'planning',  label: 'Планирование',  icon: <BrainCircuit className="w-4 h-4" />, detail: 'Разбивка темы на аналитические вопросы...' },
  { id: 'data',      label: 'Сбор данных',   icon: <Database className="w-4 h-4" />,     detail: 'Text-to-SQL → ClickHouse OLAP...' },
  { id: 'analysis',  label: 'Анализ',     icon: <Zap className="w-4 h-4" />,          detail: 'Глубокий анализ: инсайты, аномалии, тренды...' },
  { id: 'charts',    label: 'Визуализация',  icon: <BarChart3 className="w-4 h-4" />,    detail: 'Генерация интерактивных графиков...' },
  { id: 'build',     label: 'Сборка .pptx',  icon: <FileSliders className="w-4 h-4" />,  detail: 'Рендеринг слайдов, экспорт...' },
];

type StageStatus = 'pending' | 'running' | 'done' | 'error';

const CHART_TYPES = [
  { value: 'auto', label: 'Авто', icon: <Sparkles className="w-3.5 h-3.5" /> },
  { value: 'bar', label: 'Бар', icon: <BarChart2 className="w-3.5 h-3.5" /> },
  { value: 'line', label: 'Линия', icon: <TrendingUp className="w-3.5 h-3.5" /> },
  { value: 'donut', label: 'Пончик', icon: <PieChart className="w-3.5 h-3.5" /> },
  { value: 'area', label: 'Area', icon: <Activity className="w-3.5 h-3.5" /> },
  { value: 'horizontal_bar', label: 'Горизонт.', icon: <BarChart3 className="w-3.5 h-3.5" /> },
];

const AUDIENCE_OPTIONS = [
  { value: 'executive', label: 'Топ-менеджмент', desc: 'Стратегический уровень, KPI и рекомендации' },
  { value: 'analyst',   label: 'Аналитики',      desc: 'Детализированные данные и методология' },
  { value: 'board',     label: 'Совет директоров', desc: 'Краткий обзор, риски, возможности' },
];

const DETaiL_OPTIONS = [
  { value: 'standard', label: 'Стандарт',      desc: '8–12 слайдов', slides: 10 },
  { value: 'detailed',  label: 'Детальный',    desc: '12–18 слайдов', slides: 14 },
  { value: 'comprehensive', label: 'Комплексный', desc: '18–25 слайдов', slides: 20 },
];

const SUGGESTED_THEMES = [
  'Налоговые поступления по регионам за 2024 год',
  'Динамика задолженности и собираемости налогов',
  'Анализ НДС: структура, динамика, аномалии',
  'Сравнительный анализ регионов по налоговой нагрузке',
  'Тренды налога на прибыль организаций',
  'Региональный дисбаланс и пути выравнивания',
];

// StageRow
const StageRow: React.FC<{ stage: Stage; status: StageStatus; detail?: string; delay: number }> = ({
  stage, status, delay
}) => {
  const colors = {
    pending: 'text-slate-600',
    running: 'text-violet-400',
    done:    'text-emerald-400',
    error:   'text-rose-400',
  };
  const icons = {
    pending: <Circle className="w-4 h-4 text-slate-700" />,
    running: <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />,
    done:    <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
    error:   <X className="w-4 h-4 text-rose-400" />,
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay }}
      className={`flex items-center gap-3 p-3 rounded-xl transition-all duration-300 ${
        status === 'running' ? 'bg-violet-500/8 border border-violet-500/20' :
        status === 'done'    ? 'bg-emerald-500/5 border border-emerald-500/10' :
        status === 'error'   ? 'bg-rose-500/5 border border-rose-500/10' :
                               'border border-transparent'
      }`}
    >
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
        status === 'running' ? 'bg-violet-500/15' :
        status === 'done'    ? 'bg-emerald-500/10' :
        'bg-slate-800/80'
      }`}>
        {stage.icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-semibold transition-colors ${colors[status]}`}>
          {stage.label}
        </div>
        {status === 'running' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-xs text-violet-400/70 mt-0.5 truncate"
          >
            {stage.detail}
          </motion.div>
        )}
        {status === 'done' && (
          <div className="text-xs text-emerald-500/60 mt-0.5">Завершено</div>
        )}
        {status === 'error' && (
          <div className="text-xs text-rose-400/70 mt-0.5">Ошибка</div>
        )}
      </div>
      <div className="flex-shrink-0">{icons[status]}</div>
    </motion.div>
  );
};

// Question Row
interface QuestionItem {
  id: string;
  text: string;
  chartType: string;
}

const QuestionRow: React.FC<{
  item: QuestionItem;
  index: number;
  onChange: (id: string, field: 'text' | 'chartType', value: string) => void;
  onRemove: (id: string) => void;
  canRemove: boolean;
}> = ({ item, index, onChange, onRemove, canRemove }) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -10, height: 0 }}
    className="flex items-start gap-2 bg-slate-900/60 rounded-xl border border-white/5 p-3"
  >
    <div className="w-6 h-6 flex items-center justify-center text-slate-600 text-xs font-bold flex-shrink-0 mt-1">
      {index + 1}
    </div>
    <input
      value={item.text}
      onChange={e => onChange(item.id, 'text', e.target.value)}
      placeholder={`Вопрос ${index + 1}...`}
      className="flex-1 bg-transparent border-none outline-none text-sm text-slate-200 placeholder:text-slate-600 resize-none"
    />
    <div className="flex items-center gap-1.5 flex-shrink-0">
      {CHART_TYPES.slice(0, 4).map(ct => (
        <button
          key={ct.value}
          title={ct.label}
          onClick={() => onChange(item.id, 'chartType', ct.value)}
          className={`w-6 h-6 rounded-md flex items-center justify-center transition-all ${
            item.chartType === ct.value
              ? 'bg-violet-500/25 text-violet-300 border border-violet-500/30'
              : 'text-slate-600 hover:text-slate-400 hover:bg-slate-800'
          }`}
        >
          {ct.icon}
        </button>
      ))}
      {canRemove && (
        <button
          onClick={() => onRemove(item.id)}
          className="w-6 h-6 rounded-md text-slate-600 hover:text-rose-400 hover:bg-rose-500/10 flex items-center justify-center transition-all ml-1"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  </motion.div>
);

// Progress Bar
const ProgressBar: React.FC<{ stages: Record<string, StageStatus> }> = ({ stages }) => {
  const total = STAGES.length;
  const done = Object.values(stages).filter(s => s === 'done').length;
  const running = Object.values(stages).filter(s => s === 'running').length;
  const pct = Math.round(((done + running * 0.5) / total) * 100);

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-slate-500">
        <span>Прогресс</span>
        <span className="text-violet-400 font-semibold">{pct}%</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className="h-full bg-gradient-to-r from-violet-600 to-violet-400 rounded-full"
        />
      </div>
    </div>
  );
};

// Main Modal
interface PresentationGeneratorModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string | null;
}

export const PresentationGeneratorModal: React.FC<PresentationGeneratorModalProps> = ({
  isOpen, onClose, token
}) => {
  const [theme, setTheme] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stageStatuses, setStageStatuses] = useState<Record<string, StageStatus>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [audience, setAudience] = useState('executive');
  const [detailLevel, setDetailLevel] = useState('detailed');
  const [mode, setMode] = useState<'theme' | 'questions'>('theme');
  const [questions, setQuestions] = useState<QuestionItem[]>([
    { id: '1', text: '', chartType: 'auto' },
    { id: '2', text: '', chartType: 'auto' },
    { id: '3', text: '', chartType: 'auto' },
  ]);

  const addPresentation = useChatStore(s => s.addPresentation);
  const setActiveTab = useChatStore(s => s.setActiveTab);

  const numSlides = DETaiL_OPTIONS.find(d => d.value === detailLevel)?.slides || 14;

  const addQuestion = useCallback(() => {
    if (questions.length >= 12) return;
    setQuestions(prev => [...prev, { id: `q_${Date.now()}`, text: '', chartType: 'auto' }]);
  }, [questions.length]);

  const removeQuestion = useCallback((id: string) => {
    setQuestions(prev => prev.filter(q => q.id !== id));
  }, []);

  const updateQuestion = useCallback((id: string, field: 'text' | 'chartType', value: string) => {
    setQuestions(prev => prev.map(q => q.id === id ? { ...q, [field]: value } : q));
  }, []);

  const advanceStages = async (abortSignal: AbortSignal) => {
    const delays = [0, 2500, 10000, 18000, 26000];
    const stageIds = STAGES.map(s => s.id);
    for (let i = 0; i < stageIds.length; i++) {
      if (abortSignal.aborted) return;
      await new Promise<void>(r => setTimeout(r, i === 0 ? 0 : delays[i] - delays[i - 1]));
      if (abortSignal.aborted) return;
      setStageStatuses(prev => {
        const next = { ...prev };
        if (i > 0) next[stageIds[i - 1]] = 'done';
        next[stageIds[i]] = 'running';
        return next;
      });
    }
  };

  const handleGenerate = async () => {
    const themeVal = theme.trim();
    if (mode === 'theme' && !themeVal) return;
    if (mode === 'questions' && questions.every(q => !q.text.trim())) return;

    setIsGenerating(true);
    setError(null);
    setStageStatuses({ planning: 'running' });

    const animationAbortCtrl = new AbortController();
    advanceStages(animationAbortCtrl.signal);

    try {
      const body: Record<string, unknown> = {
        num_slides: numSlides,
        include_title: true,
        include_recommendations: true,
        audience,
        detail_level: detailLevel,
      };

      if (mode === 'theme') {
        body.mode = 'Свободная тема';
        body.overall_theme = themeVal;
      } else {
        // Questions mode: send questions with chart preferences
        const validQs = questions.filter(q => q.text.trim());
        body.mode = 'Вопросы';
        body.questions = validQs.map(q => ({
          text: q.text.trim(),
          chart_type: q.chartType !== 'auto' ? q.chartType : null,
        }));
        body.overall_theme = validQs.map(q => q.text.trim()).join(', ');
      }

      const res = await fetch(`${API}/generate_presentation`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });

      animationAbortCtrl.abort();

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();

      setStageStatuses(Object.fromEntries(STAGES.map(s => [s.id, 'done'])));

      const id = data.presentation_id || `pres_${Date.now()}`;
      addPresentation({
        id,
        title: (themeVal || questions.find(q => q.text.trim())?.text || 'Презентация').slice(0, 60),
        theme: themeVal || questions.map(q => q.text).join(', '),
        timestamp: Date.now(),
        pptx_path: data.pptx_path || '',
        num_slides: data.num_slides || numSlides,
        slide_png_paths: data.slide_png_paths || [],
        slides: data.slides || [],
        reasoning: data.reasoning,
      });

      await new Promise(r => setTimeout(r, 700));
      setActiveTab('presentation');
      onClose();
      // Reset state
      setTheme('');
      setIsGenerating(false);
      setStageStatuses({});
      setQuestions([
        { id: '1', text: '', chartType: 'auto' },
        { id: '2', text: '', chartType: 'auto' },
        { id: '3', text: '', chartType: 'auto' },
      ]);

    } catch (e: unknown) {
      animationAbortCtrl.abort();
      if (e instanceof Error && e.name === 'AbortError') return;
      const msg = e instanceof Error ? e.message : 'Произошла ошибка';
      setError(msg);
      setStageStatuses(prev => {
        const next = { ...prev };
        const running = Object.entries(next).find(([, v]) => v === 'running');
        if (running) next[running[0]] = 'error';
        return next;
      });
      setIsGenerating(false);
    }
  };

  const canGenerate = !isGenerating && (
    (mode === 'theme' && theme.trim().length > 0) ||
    (mode === 'questions' && questions.some(q => q.text.trim()))
  );

  const selectedDetail = DETaiL_OPTIONS.find(d => d.value === detailLevel)!;

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={!isGenerating ? onClose : undefined}
            className="absolute inset-0 bg-slate-950/85 backdrop-blur-md"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 10 }}
            transition={{ type: 'spring', stiffness: 300, damping: 28 }}
            className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto custom-scrollbar"
          >
            <div className="bg-[#0d1424] border border-white/8 rounded-2xl shadow-2xl overflow-hidden">
              {/* Header */}
              <div className="relative px-6 pt-6 pb-4 border-b border-white/6">
                <div className="absolute inset-0 bg-gradient-to-br from-violet-900/15 via-transparent to-transparent" />
                <div className="relative flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-violet-600/15 border border-violet-500/25 flex items-center justify-center">
                      <Presentation className="w-5 h-5 text-violet-400" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-white">Создать презентацию</h2>
                      <p className="text-xs text-slate-500 mt-0.5">Авто-генерация • ClickHouse • Plotly</p>
                    </div>
                  </div>
                  {!isGenerating && (
                    <button onClick={onClose}
                      className="w-8 h-8 rounded-lg bg-slate-800/60 text-slate-400 hover:text-white hover:bg-slate-700 flex items-center justify-center transition-all">
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              <div className="px-6 py-5 space-y-5">
                {!isGenerating ? (
                  <>
                    {/* Mode Selector */}
                    <div className="flex gap-1 bg-slate-900/60 rounded-xl p-1 border border-white/5">
                      {[
                        { id: 'theme', label: 'По теме', icon: <Globe2 className="w-3.5 h-3.5" /> },
                        { id: 'questions', label: 'По вопросам', icon: <Target className="w-3.5 h-3.5" /> },
                      ].map(m => (
                        <button key={m.id} onClick={() => setMode(m.id as 'theme' | 'questions')}
                          className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-all ${
                            mode === m.id ? 'bg-slate-700 text-white shadow' : 'text-slate-500 hover:text-slate-300'
                          }`}>
                          {m.icon} {m.label}
                        </button>
                      ))}
                    </div>

                    {/* Theme input */}
                    {mode === 'theme' && (
                      <div className="space-y-3">
                        <div className="relative">
                          <textarea
                            value={theme}
                            onChange={e => setTheme(e.target.value)}
                            placeholder="Введите тему презентации..."
                            rows={3}
                            className="w-full bg-slate-900/70 border border-white/8 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-600 outline-none focus:border-violet-500/50 resize-none transition-colors"
                          />
                        </div>
                        {/* Suggestions */}
                        <div className="space-y-1.5">
                          <p className="text-xs text-slate-600 flex items-center gap-1.5">
                            <Lightbulb className="w-3 h-3" /> Предложения
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {SUGGESTED_THEMES.map(s => (
                              <button key={s} onClick={() => setTheme(s)}
                                className="px-2.5 py-1 rounded-lg bg-slate-800/70 border border-white/5 text-xs text-slate-400 hover:text-white hover:border-violet-500/30 hover:bg-violet-500/8 transition-all text-left">
                                {s}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Questions mode */}
                    {mode === 'questions' && (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between mb-3">
                          <p className="text-xs text-slate-500">Укажите вопросы для каждого слайда</p>
                          <span className="text-xs text-slate-600">{questions.length}/12</span>
                        </div>
                        <AnimatePresence mode="popLayout">
                          {questions.map((q, i) => (
                            <QuestionRow
                              key={q.id}
                              item={q}
                              index={i}
                              onChange={updateQuestion}
                              onRemove={removeQuestion}
                              canRemove={questions.length > 1}
                            />
                          ))}
                        </AnimatePresence>
                        {questions.length < 12 && (
                          <button onClick={addQuestion}
                            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-dashed border-white/10 text-slate-500 hover:text-slate-300 hover:border-violet-500/30 text-xs transition-all">
                            <Plus className="w-3.5 h-3.5" /> Добавить вопрос
                          </button>
                        )}
                      </div>
                    )}

                    {/* Detail Level */}
                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 uppercase tracking-wider">
                        <Settings2 className="w-3 h-3" /> Детализация
                      </label>
                      <div className="grid grid-cols-3 gap-2">
                        {DETaiL_OPTIONS.map(opt => (
                          <button key={opt.value} onClick={() => setDetailLevel(opt.value)}
                            className={`flex flex-col items-center gap-1 p-3 rounded-xl border transition-all ${
                              detailLevel === opt.value
                                ? 'border-violet-500/40 bg-violet-500/10 text-white'
                                : 'border-white/5 bg-slate-900/40 text-slate-400 hover:border-violet-500/20 hover:text-slate-200'
                            }`}>
                            <span className="text-sm font-semibold">{opt.label}</span>
                            <span className="text-[10px] text-slate-500">{opt.desc}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Advanced Options (collapsible) */}
                    <div className="border border-white/5 rounded-xl overflow-hidden">
                      <button
                        onClick={() => setShowAdvanced(v => !v)}
                        className="w-full flex items-center justify-between px-4 py-3 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 transition-all"
                      >
                        <span className="flex items-center gap-2 font-medium">
                          <Settings2 className="w-3.5 h-3.5" /> Дополнительные настройки
                        </span>
                        {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                      <AnimatePresence>
                        {showAdvanced && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="px-4 py-4 border-t border-white/5 space-y-4">
                              {/* Audience */}
                              <div className="space-y-2">
                                <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 uppercase tracking-wider">
                                  <Users className="w-3 h-3" /> Целевая аудитория
                                </label>
                                <div className="space-y-1.5">
                                  {AUDIENCE_OPTIONS.map(opt => (
                                    <button key={opt.value} onClick={() => setAudience(opt.value)}
                                      className={`w-full flex items-start gap-3 p-3 rounded-xl border text-left transition-all ${
                                        audience === opt.value
                                          ? 'border-violet-500/40 bg-violet-500/8'
                                          : 'border-white/5 bg-slate-900/30 hover:border-violet-500/20'
                                      }`}>
                                      <div className={`w-4 h-4 rounded-full border-2 flex-shrink-0 mt-0.5 transition-all ${
                                        audience === opt.value ? 'border-violet-500 bg-violet-500' : 'border-slate-600'
                                      }`} />
                                      <div>
                                        <div className={`text-sm font-medium ${audience === opt.value ? 'text-white' : 'text-slate-300'}`}>
                                          {opt.label}
                                        </div>
                                        <div className="text-xs text-slate-500 mt-0.5">{opt.desc}</div>
                                      </div>
                                    </button>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>

                    {/* Summary */}
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-900/50 border border-white/5">
                      <Info className="w-4 h-4 text-slate-500 flex-shrink-0" />
                      <p className="text-xs text-slate-500">
                        Будет создана презентация <span className="text-slate-300 font-semibold">{selectedDetail.desc}</span> для{' '}
                        <span className="text-slate-300 font-semibold">{AUDIENCE_OPTIONS.find(a => a.value === audience)?.label}</span>.
                        Среднее время подготовки: <span className="text-violet-400 font-semibold">1–3 минуты</span>.
                      </p>
                    </div>

                    {/* Error */}
                    {error && (
                      <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-rose-500/8 border border-rose-500/20">
                        <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                        <p className="text-sm text-rose-300">{error}</p>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-3">
                      <Button onClick={onClose} variant="ghost" className="flex-1 border border-white/8 text-slate-400 hover:text-white hover:bg-slate-800">
                        Отмена
                      </Button>
                      <Button
                        onClick={handleGenerate}
                        disabled={!canGenerate}
                        className="flex-1 bg-gradient-to-r from-violet-600 to-violet-700 hover:from-violet-500 hover:to-violet-600 text-white shadow-lg shadow-violet-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Sparkles className="w-4 h-4 mr-2" />
                        Создать презентацию
                        <ChevronRight className="w-4 h-4 ml-1" />
                      </Button>
                    </div>
                  </>
                ) : (
                  /* Generating state */
                  <div className="space-y-4">
                    <ProgressBar stages={stageStatuses} />
                    <div className="space-y-1">
                      {STAGES.map((stage, i) => (
                        <StageRow
                          key={stage.id}
                          stage={stage}
                          status={stageStatuses[stage.id] || 'pending'}
                          delay={i * 0.05}
                        />
                      ))}
                    </div>
                    <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-slate-900/50 border border-white/5">
                      <Sparkles className="w-4 h-4 text-violet-400 flex-shrink-0 mt-0.5 animate-pulse" />
                      <p className="text-xs text-slate-400">
                        Система анализирует данные в ClickHouse, строит графики и генерирует аналитические выводы. Это занимает 1–3 минуты.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};