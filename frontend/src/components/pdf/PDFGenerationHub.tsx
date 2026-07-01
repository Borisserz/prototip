import React, { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText, Presentation, LayoutDashboard, UploadCloud,
  X, Sparkles, Loader2, CheckCircle2, Circle, AlertCircle,
  FileCheck2, ChevronRight, File, ArrowLeft, Download,
  BookOpen, Tags, FileType2, BrainCircuit,
  Database, BarChart3, FileSliders, Zap, 
  ChevronDown, Users, Settings2, Eye, Trash2, Clock, 
  Info, CheckCircle, Timer, RotateCcw,
  FileQuestion, Layers, TrendingUp, Award, ChevronUp,
  Plus, Globe, FileStack, Cpu
} from 'lucide-react';
import { Button } from '../ui/button';
import { useChatStore, PdfGenerationHistoryItem } from '../../store/useChatStore';
import { PresentationView } from '../presentation/PresentationView';
import { exportDashboardToPDF } from '../../utils/dashboardPdfExport';
import { API_BASE } from "@/lib/config";

const API = API_BASE;
// Stage Config
const PRES_STAGES = [
  { id: 'upload',   label: 'Загрузка файла',     icon: <UploadCloud className="w-4 h-4" />,   detail: 'Передача PDF на сервер...' },
  { id: 'extract',  label: 'Извлечение текста',  icon: <FileText className="w-4 h-4" />,      detail: 'Парсинг страниц, распознавание структуры...' },
  { id: 'analyze',  label: 'Анализ',           icon: <BrainCircuit className="w-4 h-4" />,  detail: 'Извлечение тем, метаданных, ключевых вопросов...' },
  { id: 'charts',   label: 'Данные и графики',   icon: <BarChart3 className="w-4 h-4" />,     detail: 'Text-to-SQL → ClickHouse → Plotly...' },
  { id: 'build',    label: 'Сборка .pptx',       icon: <FileSliders className="w-4 h-4" />,   detail: 'Рендеринг слайдов, экспорт файла...' },
];

const DASH_STAGES = [
  { id: 'upload',   label: 'Загрузка файла',     icon: <UploadCloud className="w-4 h-4" />,      detail: 'Передача PDF на сервер...' },
  { id: 'extract',  label: 'Извлечение текста',  icon: <FileText className="w-4 h-4" />,          detail: 'Парсинг страниц, распознавание структуры...' },
  { id: 'analyze',  label: 'Анализ',           icon: <BrainCircuit className="w-4 h-4" />,     detail: 'Определение тем, KPI-метрик...' },
  { id: 'data',     label: 'OLAP Запросы',        icon: <Database className="w-4 h-4" />,         detail: 'Text-to-SQL, агрегации в ClickHouse...' },
  { id: 'build',    label: 'Сборка дашборда',    icon: <LayoutDashboard className="w-4 h-4" />,   detail: 'Генерация KPI карт, интерактивных графиков...' },
];

type StageStatus = 'pending' | 'running' | 'done' | 'error';
type OutputType = 'presentation' | 'dashboard';
type Step = 'upload' | 'choose' | 'progress' | 'result';

const AUDIENCE_OPTIONS = [
  { value: 'executive', label: 'Топ-менеджмент', desc: 'Стратегический уровень, KPI и рекомендации', icon: Award },
  { value: 'analyst',   label: 'Аналитики',      desc: 'Детализированные данные и методология',     icon: TrendingUp },
  { value: 'board',     label: 'Совет директоров', desc: 'Краткий обзор, риски, возможности',         icon: Globe },
];

const DETaiL_OPTIONS = [
  { value: 'standard',      label: 'Стандарт',    desc: '8–12 слайдов',  slides: 10 },
  { value: 'detailed',      label: 'Детальный',   desc: '12–18 слайдов', slides: 14 },
  { value: 'comprehensive', label: 'Комплексный', desc: '18–25 слайдов', slides: 20 },
];

// Helpers
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}с`;
  return `${Math.floor(s / 60)}м ${s % 60}с`;
}

// StageRow
const StageRow: React.FC<{ stage: any; status: StageStatus; delay: number }> = ({ stage, status, delay }) => {
  const colors = {
    pending: 'text-slate-600', running: 'text-violet-400',
    done: 'text-emerald-400',  error: 'text-rose-400',
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
        status === 'done'    ? 'bg-emerald-500/10' : 'bg-slate-800/80'
      }`}>
        {stage.icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-semibold transition-colors ${colors[status]}`}>{stage.label}</div>
        {status === 'running' && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-xs text-violet-400/70 mt-0.5 truncate">
            {stage.detail}
          </motion.div>
        )}
        {status === 'done' && <div className="text-xs text-emerald-500/60 mt-0.5">Завершено</div>}
        {status === 'error' && <div className="text-xs text-rose-400/70 mt-0.5">Ошибка</div>}
      </div>
      <div className="flex-shrink-0">{icons[status]}</div>
    </motion.div>
  );
};

// ProgressBar
const ProgressBar: React.FC<{ stages: Record<string, StageStatus>; total: number }> = ({ stages, total }) => {
  const done = Object.values(stages).filter(s => s === 'done').length;
  const running = Object.values(stages).filter(s => s === 'running').length;
  const pct = Math.round(((done + running * 0.5) / total) * 100);

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-slate-500">
        <span>Прогресс подготовки</span>
        <motion.span
          key={pct}
          initial={{ scale: 1.2, color: '#a78bfa' }}
          animate={{ scale: 1, color: '#a78bfa' }}
          className="font-bold text-violet-400"
        >{pct}%</motion.span>
      </div>
      <div className="h-2 bg-slate-800/80 rounded-full overflow-hidden relative">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="h-full rounded-full relative"
          style={{ background: 'linear-gradient(90deg, #7c3aed, #8b5cf6, #a78bfa)' }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
        </motion.div>
      </div>
    </div>
  );
};

// File Card
const FileCard: React.FC<{
  file: File;
  onRemove: () => void;
  isOnly: boolean;
}> = ({ file, onRemove, isOnly }) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -8, height: 0 }}
    className="flex items-center gap-3 p-3 bg-slate-800/50 border border-slate-700/50 rounded-xl group"
  >
    <div className="w-9 h-9 rounded-xl bg-rose-500/15 border border-rose-500/25 flex items-center justify-center flex-shrink-0">
      <FileText className="w-4 h-4 text-rose-400" />
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-sm text-slate-200 font-semibold truncate">{file.name}</p>
      <p className="text-xs text-slate-500">{formatFileSize(file.size)} · PDF</p>
    </div>
    {!isOnly && (
      <button
        onClick={onRemove}
        className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    )}
    {isOnly && (
      <button
        onClick={onRemove}
        className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    )}
  </motion.div>
);

// History Item
const HistoryItem: React.FC<{
  gen: PdfGenerationHistoryItem;
  onClick: () => void;
  onOpen: () => void;
  onDelete: () => void;
}> = ({ gen, onClick, onOpen, onDelete }) => (
  <motion.div
    initial={{ opacity: 0, x: -6 }}
    animate={{ opacity: 1, x: 0 }}
    className="group flex items-center gap-3 p-3 bg-slate-800/30 border border-slate-700/30 rounded-xl hover:border-violet-500/30 hover:bg-slate-800/50 transition-all cursor-pointer"
    onClick={onClick}
  >
    <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${
      gen.output_type === 'presentation'
        ? 'bg-violet-500/15 border border-violet-500/20'
        : 'bg-emerald-500/15 border border-emerald-500/20'
    }`}>
      {gen.output_type === 'presentation'
        ? <Presentation className="w-4 h-4 text-violet-400" />
        : <LayoutDashboard className="w-4 h-4 text-emerald-400" />
      }
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-sm text-slate-200 font-semibold truncate">{gen.title}</p>
      <div className="flex items-center gap-2 mt-0.5">
        <span className="text-[10px] text-slate-500 truncate">{gen.file_name}</span>
        <span className="text-slate-700">·</span>
        <span className="text-[10px] text-slate-500">{new Date(gen.timestamp).toLocaleDateString('ru-RU')}</span>
      </div>
    </div>
    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button
        onClick={e => { e.stopPropagation(); onOpen(); }}
        className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-white/8 transition-all"
        title="Открыть"
      >
        <Eye className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={e => { e.stopPropagation(); onDelete(); }}
        className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-rose-500/10 transition-all"
        title="Удалить"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  </motion.div>
);

// Result Card
const ResultView: React.FC<{
  result: PdfGenerationHistoryItem;
  elapsed: number;
  onOpen: () => void;
  onDownload?: () => void;
  onNew: () => void;
}> = ({ result, elapsed, onOpen, onDownload, onNew }) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.98, y: 16 }}
    animate={{ opacity: 1, scale: 1, y: 0 }}
    transition={{ type: 'spring', stiffness: 300, damping: 28 }}
    className="space-y-4"
  >
    {/* Success Banner */}
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-3 px-4 py-3.5 rounded-2xl bg-gradient-to-r from-emerald-500/10 to-emerald-500/5 border border-emerald-500/20"
    >
      <div className="w-9 h-9 rounded-xl bg-emerald-500/20 flex items-center justify-center flex-shrink-0">
        <CheckCircle className="w-5 h-5 text-emerald-400" />
      </div>
      <div className="flex-1">
        <p className="text-sm font-bold text-emerald-300">Генерация завершена!</p>
        <p className="text-xs text-emerald-500/70">
          {result.output_type === 'presentation' ? 'Презентация создана' : 'Дашборд создан'} за {formatElapsed(elapsed)}
        </p>
      </div>
      <div className="flex items-center gap-1.5 text-xs text-emerald-500/60">
        <Timer className="w-3 h-3" />
        {formatElapsed(elapsed)}
      </div>
    </motion.div>

    {/* Doc Info Card */}
    <div className={`rounded-2xl overflow-hidden border ${
      result.output_type === 'presentation'
        ? 'border-violet-500/20 bg-gradient-to-br from-violet-900/15 to-slate-900/80'
        : 'border-emerald-500/20 bg-gradient-to-br from-emerald-900/15 to-slate-900/80'
    }`}>
      <div className="px-5 py-4 border-b border-white/5">
        <div className="flex items-start gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
            result.output_type === 'presentation'
              ? 'bg-violet-600/20 border border-violet-500/30'
              : 'bg-emerald-600/20 border border-emerald-500/30'
          }`}>
            {result.output_type === 'presentation'
              ? <Presentation className="w-5 h-5 text-violet-400" />
              : <LayoutDashboard className="w-5 h-5 text-emerald-400" />
            }
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-bold text-white leading-tight mb-1">{result.title}</h3>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                result.output_type === 'presentation'
                  ? 'bg-violet-500/20 text-violet-300'
                  : 'bg-emerald-500/20 text-emerald-300'
              }`}>
                {result.output_type === 'presentation' ? 'Презентация' : 'Дашборд'}
              </span>
              <span className="text-[11px] text-slate-500 flex items-center gap-1">
                <FileText className="w-3 h-3" /> {result.file_name}
              </span>
              <span className="text-[11px] text-slate-500 flex items-center gap-1">
                <BookOpen className="w-3 h-3" /> {result.num_pages} стр.
              </span>
              <span className="text-[11px] text-slate-500 flex items-center gap-1">
                <Clock className="w-3 h-3" /> {new Date(result.timestamp).toLocaleDateString('ru-RU')}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="px-5 py-4 space-y-3">
        {/* Summary */}
        {result.doc_summary && (
          <div>
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
              <Info className="w-3 h-3" /> О документе
            </p>
            <p className="text-sm text-slate-300 leading-relaxed">{result.doc_summary}</p>
          </div>
        )}

        {/* Topics */}
        {result.doc_topics && result.doc_topics.length > 0 && (
          <div>
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
              <Tags className="w-3 h-3" /> Ключевые темы
            </p>
            <div className="flex flex-wrap gap-1.5">
              {result.doc_topics.slice(0, 7).map((topic, i) => (
                <motion.span
                  key={i}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.04 }}
                  className="text-xs px-2.5 py-1 rounded-lg bg-slate-800/80 border border-white/6 text-slate-300 hover:border-violet-500/30 hover:text-slate-200 transition-colors"
                >
                  {topic}
                </motion.span>
              ))}
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-3 gap-2 pt-1">
          {[
            { label: 'Страниц PDF', value: result.num_pages || '—', icon: FileText },
            { label: result.output_type === 'presentation' ? 'Слайдов' : 'Графиков', value: result.output_type === 'dashboard' ? (result.dashboard_data?.charts?.length || '—') : (result.slides?.length || '—'), icon: Layers },
            { label: 'время подготовки', value: formatElapsed(elapsed), icon: Timer },
          ].map(({ label, value, icon: Icon }) => (
            <div key={label} className="bg-slate-800/50 rounded-xl border border-white/5 p-3 text-center">
              <Icon className="w-4 h-4 text-slate-500 mx-auto mb-1.5" />
              <div className="text-base font-bold text-white">{value}</div>
              <div className="text-[10px] text-slate-600 mt-0.5">{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>

    {/* Action Buttons */}
    <div className="space-y-2">
      <Button
        onClick={onOpen}
        className={`w-full font-semibold h-11 ${
          result.output_type === 'presentation'
            ? 'bg-gradient-to-r from-violet-600 to-violet-700 hover:from-violet-500 hover:to-violet-600 shadow-lg shadow-violet-500/20'
            : 'bg-gradient-to-r from-emerald-600 to-emerald-700 hover:from-emerald-500 hover:to-emerald-600 shadow-lg shadow-emerald-500/20'
        } text-white`}
      >
        <Eye className="w-4 h-4 mr-2" />
        {result.output_type === 'presentation' ? 'Открыть презентацию' : 'Открыть дашборд'}
        <ChevronRight className="w-4 h-4 ml-1.5" />
      </Button>
      <div className="flex gap-2">
        {result.output_type === 'presentation' && onDownload && result.pptx_path && (
          <Button variant="outline" onClick={onDownload}
            className="flex-1 border-slate-600 hover:bg-slate-700/50 text-slate-300 hover:text-white h-10">
            <Download className="w-4 h-4 mr-2" /> Скачать .pptx
          </Button>
        )}
        {result.output_type === 'dashboard' && onDownload && (
          <Button variant="outline" onClick={onDownload}
            className="flex-1 border-emerald-600/50 hover:bg-emerald-700/30 text-emerald-300 hover:text-emerald-100 h-10">
            <Download className="w-4 h-4 mr-2" /> Скачать .pdf
          </Button>
        )}
        <Button variant="outline" onClick={onNew}
          className="flex-1 border-slate-600 hover:bg-slate-700/50 text-slate-300 hover:text-white h-10">
          <Plus className="w-4 h-4 mr-2" /> Новый
        </Button>
      </div>
    </div>
  </motion.div>
);

// Main Component
interface PDFGenerationHubProps {
  token: string | null;
}

export const PDFGenerationHub: React.FC<PDFGenerationHubProps> = ({ token }) => {
  const [step, setStep] = useState<Step>('upload');
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [outputType, setOutputType] = useState<OutputType>('presentation');
  const [audience, setAudience] = useState('executive');
  const [detailLevel, setDetailLevel] = useState('detailed');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [stageStatuses, setStageStatuses] = useState<Record<string, StageStatus>>({});
  const [error, setError] = useState<string | null>(null);
  const [currentResult, setCurrentResult] = useState<PdfGenerationHistoryItem | null>(null);
  const [viewingPresentationId, setViewingPresentationId] = useState<string | null>(null);
  const [startTime, setStartTime] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pdfGenerations = useChatStore(s => s.pdfGenerations);
  const addPdfGeneration = useChatStore(s => s.addPdfGeneration);
  const deletePdfGeneration = useChatStore(s => s.deletePdfGeneration);
  const addPresentation = useChatStore(s => s.addPresentation);
  const addDashboard = useChatStore(s => s.addDashboard);
  const setActiveDashboard = useChatStore(s => s.setActiveDashboard);
  const setActiveTab = useChatStore(s => s.setActiveTab);
  const setActivePresentation = useChatStore(s => s.setActivePresentation);

  const stages = outputType === 'presentation' ? PRES_STAGES : DASH_STAGES;

  // Elapsed timer
  useEffect(() => {
    if (step === 'progress') {
      setStartTime(Date.now());
      setElapsed(0);
      elapsedRef.current = setInterval(() => {
        setElapsed(Date.now() - startTime);
      }, 500);
    } else {
      if (elapsedRef.current) clearInterval(elapsedRef.current);
    }
    return () => { if (elapsedRef.current) clearInterval(elapsedRef.current); };
  }, [step]);

  // File Handling
  const handleFiles = useCallback((newFiles: FileList | File[]) => {
    const pdfs = Array.from(newFiles).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) return;
    setFiles(prev => {
      const existing = new Set(prev.map(f => f.name));
      return [...prev, ...pdfs.filter(f => !existing.has(f.name))].slice(0, 5);
    });
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  }, []);

  // Stage Animation
  const advanceStages = async (signal: AbortSignal, outputT: OutputType) => {
    const stageList = outputT === 'presentation' ? PRES_STAGES : DASH_STAGES;
    const ids = stageList.map(s => s.id);
    const delays = [800, 3000, 8000, 18000, 28000]; // cumulative ms
    for (let i = 0; i < ids.length; i++) {
      if (signal.aborted) return;
      const waitMs = i === 0 ? delays[0] : delays[i] - delays[i - 1];
      await new Promise<void>(r => setTimeout(r, waitMs));
      if (signal.aborted) return;
      setStageStatuses(prev => {
        const next = { ...prev };
        if (i > 0) next[ids[i - 1]] = 'done';
        next[ids[i]] = 'running';
        return next;
      });
    }
  };

  // Generate
  const handleGenerate = async () => {
    if (files.length === 0) return;

    setStep('progress');
    setError(null);
    setStageStatuses({ [stages[0].id]: 'running' });
    const t0 = Date.now();
    setStartTime(t0);

    const abortCtrl = new AbortController();
    advanceStages(abortCtrl.signal, outputType);

    try {
      const formData = new FormData();
      formData.append('file', files[0]);
      formData.append('output_type', outputType);
      formData.append('audience', audience);
      formData.append('detail_level', detailLevel);

      const res = await fetch(`${API}/api/v1/pdf/analyze`, {
        method: 'POST',
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: formData,
      });

      abortCtrl.abort();

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}: Ошибка сервера`);
      }

      const data = await res.json();
      setStageStatuses(Object.fromEntries(stages.map(s => [s.id, 'done'])));

      const totalElapsed = Date.now() - t0;
      setElapsed(totalElapsed);

      const id = `pdf_${Date.now()}`;
      const item: PdfGenerationHistoryItem = {
        id,
        title: data.doc_title || files[0].name,
        file_name: data.file_name || files[0].name,
        output_type: outputType,
        timestamp: Date.now(),
        doc_summary: data.doc_summary || '',
        doc_topics: data.doc_topics || [],
        doc_type: data.doc_type || 'документ',
        num_pages: data.num_pages || 0,
        pptx_path: data.pptx_path,
        slide_png_paths: data.slide_png_paths || [],
        slides: data.slides || [],
        dashboard_data: data.dashboard_data,
      };

      addPdfGeneration(item);

      // Bridge to unified presentation/dashboard history
      if (outputType === 'presentation' && data.pptx_path) {
        const presId = `${id}_pres`;
        addPresentation({
          id: presId,
          title: data.doc_title || files[0].name,
          theme: `Из PDF: ${files[0].name}`,
          timestamp: Date.now(),
          pptx_path: data.pptx_path || '',
          num_slides: data.num_slides || data.slides?.length || 0,
          slide_png_paths: data.slide_png_paths || [],
          slides: data.slides || [],
          reasoning: data.reasoning,
        });
        setActivePresentation(presId);
      } else if (outputType === 'dashboard') {
        const dd = data.dashboard_data || {
          title: "Пустой дашборд",
          summary: "Сервер вернул пустой результат",
          charts: [],
          kpi_cards: [],
          insights: ["Данных нет"],
          recommendations: [],
          reasoning: "Ошибка на стороне сервера"
        };
        addDashboard({
          id: `${id}_dash`,
          title: data.doc_title || files[0].name,
          timestamp: Date.now(),
          data: JSON.stringify(dd),
        });
      }

      setCurrentResult(item);
      await new Promise(r => setTimeout(r, 400));
      setStep('result');

    } catch (e: unknown) {
      abortCtrl.abort();
      if (e instanceof Error && e.name === 'AbortError') return;
      const msg = e instanceof Error ? e.message : 'Произошла неизвестная ошибка';
      setError(msg);
      setStageStatuses(prev => {
        const next = { ...prev };
        const running = Object.entries(next).find(([, v]) => v === 'running');
        if (running) next[running[0]] = 'error';
        return next;
      });
    }
  };

  const handleOpenResult = (item: PdfGenerationHistoryItem) => {
    if (item.output_type === 'presentation') {
      // Navigate to presentation tab
      const presId = `${item.id}_pres`;
      setActivePresentation(presId);
      setActiveTab('presentation');
    } else {
      const dashId = `${item.id}_dash`;
      setActiveDashboard(dashId);
      setActiveTab('dashboard');
    }
  };

  const handleDownload = async (item: PdfGenerationHistoryItem) => {
    if (item.output_type === 'dashboard') {
      if (item.dashboard_data) {
        try {
          await exportDashboardToPDF(item.dashboard_data);
        } catch (e) {
          console.error('PDF export failed:', e);
        }
      }
      return;
    }
    if (!item.pptx_path) return;
    const link = document.createElement('a');
    link.href = `${API}/api/v1/download?file=${encodeURIComponent(item.pptx_path)}`;
    link.download = item.pptx_path.split('/').pop() || 'presentation.pptx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const resetState = () => {
    setStep('upload');
    setError(null);
    setStageStatuses({});
    setCurrentResult(null);
    setElapsed(0);
  };

  // Presentation sub-view
  if (viewingPresentationId) {
    return (
      <div className="h-full flex flex-col">
        <div className="flex items-center gap-2 px-2 py-2 border-b border-white/5 flex-shrink-0">
          <button
            onClick={() => setViewingPresentationId(null)}
            className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-white transition-colors px-2 py-1 rounded-lg hover:bg-white/5"
          >
            <ArrowLeft className="w-4 h-4" /> Назад к подготовке
          </button>
        </div>
        <div className="flex-1 overflow-hidden">
          <PresentationView />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex flex-col h-full overflow-y-auto custom-scrollbar px-1 py-1">
        <AnimatePresence mode="wait">

          {/* Upload */}
          {step === 'upload' && (
            <motion.div
              key="upload"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-4"
            >
              {/* Drop Zone */}
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={`relative rounded-2xl border-2 border-dashed p-8 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all duration-300 select-none ${
                  isDragging
                    ? 'border-violet-500/70 bg-violet-500/10 scale-[1.01]'
                    : files.length > 0
                    ? 'border-emerald-500/40 bg-emerald-500/5 p-5'
                    : 'border-white/10 bg-slate-900/40 hover:border-violet-500/30 hover:bg-slate-900/60'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  multiple
                  className="hidden"
                  onChange={e => e.target.files && handleFiles(e.target.files)}
                />

                {files.length === 0 ? (
                  <>
                    <motion.div
                      animate={isDragging
                        ? { scale: 1.15, rotate: 5 }
                        : { scale: 1, rotate: 0 }
                      }
                      transition={{ type: 'spring', stiffness: 300 }}
                      className={`w-16 h-16 rounded-2xl flex items-center justify-center ${
                        isDragging
                          ? 'bg-violet-500/30 border-2 border-violet-400/50'
                          : 'bg-slate-800/80 border border-white/8'
                      }`}
                    >
                      <UploadCloud className={`w-8 h-8 ${isDragging ? 'text-violet-300' : 'text-slate-400'}`} />
                    </motion.div>
                    <div className="text-center">
                      <p className={`text-sm font-bold ${isDragging ? 'text-violet-300' : 'text-slate-200'}`}>
                        {isDragging ? 'Отпустите файлы здесь' : 'Перетащите PDF или нажмите'}
                      </p>
                      <p className="text-xs text-slate-600 mt-1">До 5 PDF файлов · Любой размер</p>
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
                        <Cpu className="w-3 h-3" /> Анализ
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
                        <Database className="w-3 h-3" /> RAG-индексация
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
                        <FileStack className="w-3 h-3" /> Экспорт .pptx
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="w-full text-center">
                    <p className="text-xs text-emerald-400 font-semibold flex items-center justify-center gap-1.5">
                      <CheckCircle className="w-3.5 h-3.5" /> {files.length} файл{files.length > 1 ? 'а' : ''} готов{files.length > 1 ? 'о' : ''}
                    </p>
                    <p className="text-[11px] text-slate-600 mt-0.5">Нажмите для добавления ещё</p>
                  </div>
                )}
              </div>

              {/* File List */}
              <AnimatePresence>
                {files.length > 0 && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
                    {files.map((file) => (
                      <FileCard
                        key={file.name}
                        file={file}
                        onRemove={() => setFiles(prev => prev.filter(f => f.name !== file.name))}
                        isOnly={files.length === 1}
                      />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>

              {files.length > 0 && (
                <Button
                  onClick={() => setStep('choose')}
                  className="w-full h-11 bg-gradient-to-r from-violet-600 to-violet-700 hover:from-violet-500 hover:to-violet-600 text-white shadow-lg shadow-violet-500/20 font-semibold"
                >
                  Выбрать тип отчета <ChevronRight className="w-4 h-4 ml-1.5" />
                </Button>
              )}

              {/* History */}
              {pdfGenerations.length > 0 && (
                <div className="border-t border-white/5 pt-4">
                  <button
                    onClick={() => setShowHistory(v => !v)}
                    className="w-full flex items-center justify-between text-xs font-bold text-slate-500 uppercase tracking-wider hover:text-slate-300 transition-colors mb-3"
                  >
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-3 h-3" /> История PDF ({pdfGenerations.length})
                    </span>
                    {showHistory ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                  <AnimatePresence>
                    {showHistory && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden space-y-2"
                      >
                        {pdfGenerations.map(gen => (
                          <HistoryItem
                            key={gen.id}
                            gen={gen}
                            onClick={() => { setCurrentResult(gen); setElapsed(0); setStep('result'); }}
                            onOpen={() => handleOpenResult(gen)}
                            onDelete={() => deletePdfGeneration(gen.id)}
                          />
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </motion.div>
          )}

          {/* Choose */}
          {step === 'choose' && (
            <motion.div
              key="choose"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              {/* Header */}
              <div className="flex items-center gap-2.5">
                <button
                  onClick={() => setStep('upload')}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-all flex-shrink-0"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-white">Выберите тип отчета</h3>
                  <p className="text-xs text-slate-500 truncate">{files[0]?.name}</p>
                </div>
              </div>

              {/* Output Type Cards */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  {
                    type: 'presentation' as OutputType,
                    icon: <Presentation className="w-7 h-7" />,
                    accent: 'violet',
                    label: 'Презентация',
                    desc: 'Слайды с аналитикой, графиками и выводами',
                    features: ['Авто-слайды из PDF', 'Графики ClickHouse', 'Экспорт .pptx', 'Онлайн-просмотр'],
                  },
                  {
                    type: 'dashboard' as OutputType,
                    icon: <LayoutDashboard className="w-7 h-7" />,
                    accent: 'emerald',
                    label: 'Дашборд',
                    desc: 'KPI карты и интерактивные графики',
                    features: ['KPI карты', 'Интерактивные графики', 'OLAP-запросы', 'Аномалии и тренды'],
                  },
                ].map(opt => {
                  const isSelected = outputType === opt.type;
                  return (
                    <motion.button
                      key={opt.type}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => setOutputType(opt.type)}
                      className={`relative p-4 rounded-2xl border text-left transition-all duration-200 overflow-hidden ${
                        isSelected
                          ? opt.accent === 'violet'
                            ? 'border-violet-500/50 bg-violet-500/10 shadow-lg shadow-violet-500/10'
                            : 'border-emerald-500/50 bg-emerald-500/10 shadow-lg shadow-emerald-500/10'
                          : 'border-white/8 bg-slate-900/40 hover:border-white/15 hover:bg-slate-900/60'
                      }`}
                    >
                      {isSelected && (
                        <motion.div
                          initial={{ scale: 0 }}
                          animate={{ scale: 1 }}
                          className={`absolute top-2.5 right-2.5 w-5 h-5 rounded-full flex items-center justify-center ${
                            opt.accent === 'violet' ? 'bg-violet-500' : 'bg-emerald-500'
                          }`}
                        >
                          <CheckCircle className="w-3.5 h-3.5 text-white" />
                        </motion.div>
                      )}
                      <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-3 transition-colors ${
                        isSelected
                          ? opt.accent === 'violet' ? 'bg-violet-600/25 text-violet-300' : 'bg-emerald-600/25 text-emerald-300'
                          : 'bg-slate-800 text-slate-400'
                      }`}>
                        {opt.icon}
                      </div>
                      <p className={`text-sm font-bold mb-1 ${isSelected ? 'text-white' : 'text-slate-200'}`}>
                        {opt.label}
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed mb-3">{opt.desc}</p>
                      <div className="space-y-1">
                        {opt.features.map((f, i) => (
                          <div key={i} className="flex items-center gap-1.5 text-xs text-slate-500">
                            <CheckCircle2 className={`w-3 h-3 flex-shrink-0 ${
                              isSelected
                                ? opt.accent === 'violet' ? 'text-violet-400' : 'text-emerald-400'
                                : 'text-slate-700'
                            }`} />
                            {f}
                          </div>
                        ))}
                      </div>
                    </motion.button>
                  );
                })}
              </div>

              {/* Advanced Options for Presentation */}
              {outputType === 'presentation' && (
                <div className="border border-white/6 rounded-xl overflow-hidden">
                  <button
                    onClick={() => setShowAdvanced(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 transition-all"
                  >
                    <span className="flex items-center gap-2 font-medium">
                      <Settings2 className="w-3.5 h-3.5" /> Настройки
                    </span>
                    <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${showAdvanced ? 'rotate-180' : ''}`} />
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
                          {/* Detail */}
                          <div>
                            <label className="text-xs font-bold text-slate-400 flex items-center gap-1.5 uppercase tracking-wider mb-2">
                              <Layers className="w-3 h-3" /> Детализация
                            </label>
                            <div className="grid grid-cols-3 gap-2">
                              {DETaiL_OPTIONS.map(opt => (
                                <button
                                  key={opt.value}
                                  onClick={() => setDetailLevel(opt.value)}
                                  className={`flex flex-col items-center gap-0.5 p-2.5 rounded-xl border transition-all text-xs ${
                                    detailLevel === opt.value
                                      ? 'border-violet-500/40 bg-violet-500/10 text-white'
                                      : 'border-white/5 bg-slate-900/40 text-slate-400 hover:border-violet-500/20'
                                  }`}
                                >
                                  <span className="font-bold">{opt.label}</span>
                                  <span className="text-slate-600 text-[10px]">{opt.desc}</span>
                                </button>
                              ))}
                            </div>
                          </div>
                          {/* Audience */}
                          <div>
                            <label className="text-xs font-bold text-slate-400 flex items-center gap-1.5 uppercase tracking-wider mb-2">
                              <Users className="w-3 h-3" /> Аудитория
                            </label>
                            <div className="space-y-1.5">
                              {AUDIENCE_OPTIONS.map(opt => {
                                const Icon = opt.icon;
                                return (
                                  <button
                                    key={opt.value}
                                    onClick={() => setAudience(opt.value)}
                                    className={`w-full flex items-center gap-3 p-2.5 rounded-xl border text-left transition-all ${
                                      audience === opt.value
                                        ? 'border-violet-500/40 bg-violet-500/8'
                                        : 'border-white/5 hover:border-violet-500/20 hover:bg-slate-800/40'
                                    }`}
                                  >
                                    <div className={`w-3.5 h-3.5 rounded-full border-2 flex-shrink-0 transition-all ${
                                      audience === opt.value ? 'border-violet-500 bg-violet-500' : 'border-slate-600'
                                    }`} />
                                    <Icon className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
                                    <div className="min-w-0">
                                      <span className="text-xs font-semibold text-slate-200">{opt.label}</span>
                                      <span className="text-[10px] text-slate-600 ml-2">{opt.desc}</span>
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* Info */}
              <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-slate-900/50 border border-white/5">
                <Zap className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-slate-500 leading-relaxed">
                  PDF будет проиндексирован в базу знаний. Система извлечёт ключевые темы и
                  сгенерирует {outputType === 'presentation' ? 'слайды с визуализациями из ClickHouse' : 'дашборд с KPI и интерактивными графиками'}.{' '}
                  <span className="text-slate-400 font-semibold">Время: 1–3 минуты.</span>
                </p>
              </div>

              {/* Generate Button */}
              <Button
                onClick={handleGenerate}
                className="w-full h-11 bg-gradient-to-r from-violet-600 to-violet-700 hover:from-violet-500 hover:to-violet-600 text-white shadow-lg shadow-violet-500/20 font-semibold"
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Сгенерировать {outputType === 'presentation' ? 'презентацию' : 'дашборд'}
                <ChevronRight className="w-4 h-4 ml-1.5" />
              </Button>
            </motion.div>
          )}

          {/* Progress */}
          {step === 'progress' && (
            <motion.div
              key="progress"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-4"
            >
              {/* Header */}
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-violet-600/15 border border-violet-500/25 flex items-center justify-center flex-shrink-0">
                  <Cpu className="w-5 h-5 text-violet-400 animate-pulse" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-white">Система обрабатывает документ...</p>
                  <p className="text-xs text-slate-500 truncate">{files[0]?.name}</p>
                </div>
                <div className="text-xs text-slate-600 flex items-center gap-1 flex-shrink-0">
                  <Timer className="w-3 h-3" />
                  <span className="tabular-nums">{formatElapsed(elapsed)}</span>
                </div>
              </div>

              <ProgressBar stages={stageStatuses} total={stages.length} />

              <div className="space-y-1">
                {stages.map((stage, i) => (
                  <StageRow
                    key={stage.id}
                    stage={stage}
                    status={stageStatuses[stage.id] || 'pending'}
                    delay={i * 0.04}
                  />
                ))}
              </div>

              {/* Error State */}
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-start gap-3 px-4 py-3 rounded-xl bg-rose-500/8 border border-rose-500/20"
                >
                  <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-rose-300 font-medium">Ошибка подготовки</p>
                    <p className="text-xs text-rose-400/70 mt-0.5 leading-relaxed">{error}</p>
                    <button
                      onClick={resetState}
                      className="mt-2 flex items-center gap-1.5 text-xs text-rose-400 hover:text-rose-300 font-medium transition-colors"
                    >
                      <RotateCcw className="w-3 h-3" /> Попробовать снова
                    </button>
                  </div>
                </motion.div>
              )}

              {/* Info */}
              {!error && (
                <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-violet-500/5 border border-violet-500/10">
                  <Sparkles className="w-4 h-4 text-violet-400 flex-shrink-0 mt-0.5 animate-pulse" />
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Система анализирует документ, формирует запросы к ClickHouse и генерирует
                    {outputType === 'presentation' ? ' слайды с интерактивными графиками.' : ' дашборд с KPI и визуализациями.'}
                    {' '}<span className="text-slate-500">Обычно занимает 1–3 минуты.</span>
                  </p>
                </div>
              )}
            </motion.div>
          )}

          {/* Result */}
          {step === 'result' && currentResult && (
            <motion.div
              key="result"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <ResultView
                result={currentResult}
                elapsed={elapsed}
                onOpen={() => handleOpenResult(currentResult)}
                onDownload={currentResult.pptx_path ? () => handleDownload(currentResult) : undefined}
                onNew={resetState}
              />
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </div>
  );
};