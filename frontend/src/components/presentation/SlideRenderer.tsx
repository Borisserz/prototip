import React, { useMemo, useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  TrendingUp, TrendingDown, BarChart2, PieChart, Target, Lightbulb,
  AlertTriangle, CheckCircle2, ArrowRight, MapPin, Globe, Zap,
  Building2, Users, DollarSign, FileText, Star, Award, Activity,
  ChevronRight, BookOpen, Shield, Cpu, BarChart, LineChart,
  Circle, AlignHorizontalDistributeCenter, Pencil, Check
} from 'lucide-react';

const API = 'http://localhost:8000';

// ─── Types ─────────────────────────────────────────────────────────────────
export interface SlideData {
  slide_idx: number;
  slide_type: string;
  title: string;
  content: string | string[] | null;
}

export interface InlineEditCallbacks {
  onTitleClick?: (slideIdx: number) => void;
  onContentClick?: (slideIdx: number) => void;
  editingTitle?: boolean;    // is the title editable right now
  editingContent?: boolean;  // is the content editable right now
  draftTitle?: string;
  draftContent?: string;
  onDraftTitleChange?: (v: string) => void;
  onDraftContentChange?: (v: string) => void;
  onSave?: () => void;
  onCancel?: () => void;
  isUpdating?: boolean;
  /** For chart slides: which chart type is currently selected */
  chartType?: string;
  onChartTypeChange?: (type: string) => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
export function toLines(content: string | string[] | null): string[] {
  if (!content) return [];
  if (Array.isArray(content)) return content.filter(Boolean);
  return content.split('\n').filter(s => s.trim());
}

// ─── Color palettes ─────────────────────────────────────────────────────────
const THEME_COLORS = [
  { bg: 'from-violet-500/15 to-purple-500/8', border: 'border-violet-500/25', icon: 'text-violet-400', badge: 'bg-violet-500/20 text-violet-300', bar: 'bg-violet-500' },
  { bg: 'from-blue-500/15 to-sky-500/8', border: 'border-blue-500/25', icon: 'text-blue-400', badge: 'bg-blue-500/20 text-blue-300', bar: 'bg-blue-500' },
  { bg: 'from-emerald-500/15 to-teal-500/8', border: 'border-emerald-500/25', icon: 'text-emerald-400', badge: 'bg-emerald-500/20 text-emerald-300', bar: 'bg-emerald-500' },
  { bg: 'from-amber-500/15 to-orange-500/8', border: 'border-amber-500/25', icon: 'text-amber-400', badge: 'bg-amber-500/20 text-amber-300', bar: 'bg-amber-500' },
  { bg: 'from-rose-500/15 to-pink-500/8', border: 'border-rose-500/25', icon: 'text-rose-400', badge: 'bg-rose-500/20 text-rose-300', bar: 'bg-rose-500' },
  { bg: 'from-cyan-500/15 to-sky-500/8', border: 'border-cyan-500/25', icon: 'text-cyan-400', badge: 'bg-cyan-500/20 text-cyan-300', bar: 'bg-cyan-500' },
];

const THEME_ICONS = [Target, Globe, BarChart2, Zap, Shield, Cpu, Activity, Award];
const REC_ICONS = [ArrowRight, Zap, Target, Star, Shield, Award];

const CHART_TYPES = [
  { id: 'bar', label: 'Bar', icon: BarChart },
  { id: 'line', label: 'Line', icon: LineChart },
  { id: 'donut', label: 'Donut', icon: Circle },
  { id: 'pie', label: 'Pie', icon: PieChart },
  { id: 'horizontal_bar', label: 'H-Bar', icon: AlignHorizontalDistributeCenter },
];

// ─── Inline Edit Overlay ─────────────────────────────────────────────────────
const InlineEditOverlay: React.FC<{
  type: 'title' | 'content';
  value: string;
  multiline?: boolean;
  onSave: (v: string) => void;
  onCancel: () => void;
}> = ({ type, value, multiline = false, onSave, onCancel }) => {
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLTextAreaElement | HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); ref.current?.select(); }, []);

  const commit = () => { if (draft.trim()) onSave(draft.trim()); };
  const handleKey = (e: React.KeyboardEvent) => {
    if (!multiline && e.key === 'Enter') { e.preventDefault(); commit(); }
    if (e.key === 'Escape') onCancel();
    if (multiline && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) commit();
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className="absolute inset-0 z-30 flex items-center justify-center p-8"
      style={{ background: 'rgba(8,13,26,0.92)', backdropFilter: 'blur(4px)' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div className="w-full max-w-2xl flex flex-col gap-3">
        <div className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">
          {type === 'title' ? '✏️ Редактировать заголовок' : '✏️ Редактировать содержимое'}
        </div>
        {multiline ? (
          <textarea
            ref={ref as React.RefObject<HTMLTextAreaElement>}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={handleKey}
            rows={8}
            className="w-full bg-slate-900 border-2 border-violet-500/60 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-violet-400 resize-none"
            placeholder={type === 'content' ? 'Каждая строка — отдельный пункт списка...' : ''}
          />
        ) : (
          <input
            ref={ref as React.RefObject<HTMLInputElement>}
            type="text"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={handleKey}
            className="w-full bg-slate-900 border-2 border-violet-500/60 rounded-xl px-4 py-3 text-lg font-bold text-white focus:outline-none focus:border-violet-400"
          />
        )}
        <div className="flex items-center gap-3">
          <button
            onClick={commit}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold transition-colors shadow-lg shadow-violet-500/20"
          >
            <Check className="w-4 h-4" /> Сохранить
          </button>
          <button onClick={onCancel} className="px-4 py-2.5 rounded-xl text-sm text-slate-400 hover:text-white transition-colors">
            Отмена
          </button>
          {multiline && (
            <span className="text-[10px] text-slate-600 ml-auto">Ctrl+Enter — сохранить · Escape — отмена</span>
          )}
        </div>
      </div>
    </motion.div>
  );
};

// ─── Editable Wrapper ────────────────────────────────────────────────────────
const EditableZone: React.FC<{
  children: React.ReactNode;
  label: string;
  onEdit: () => void;
  editMode: boolean;
}> = ({ children, label, onEdit, editMode }) => {
  const [hovered, setHovered] = useState(false);
  if (!editMode) return <>{children}</>;
  return (
    <div
      className="relative group cursor-pointer"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onEdit}
    >
      {children}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 border-2 border-dashed border-violet-500/60 rounded-lg bg-violet-500/5 flex items-center justify-center pointer-events-none z-10"
          >
            <div className="bg-violet-600 text-white text-[11px] font-bold px-2 py-1 rounded-md flex items-center gap-1 shadow-lg">
              <Pencil className="w-3 h-3" /> {label}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── Chart Type Selector ─────────────────────────────────────────────────────
const ChartTypeSelector: React.FC<{
  current?: string;
  onChange: (t: string) => void;
  isUpdating?: boolean;
}> = ({ current, onChange, isUpdating }) => (
  <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-20">
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-1.5 bg-slate-900/95 backdrop-blur border border-white/15 rounded-xl px-3 py-2 shadow-xl"
    >
      <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider mr-1">Тип</span>
      {CHART_TYPES.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          disabled={isUpdating}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${
            current === id
              ? 'bg-violet-600 text-white shadow-md shadow-violet-500/20'
              : 'text-slate-400 hover:bg-slate-800 hover:text-white'
          }`}
        >
          <Icon className="w-3 h-3" />
          {label}
        </button>
      ))}
      {isUpdating && <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin ml-1" />}
    </motion.div>
  </div>
);

// ─── TITLE SLIDE ─────────────────────────────────────────────────────────────
const TitleSlide: React.FC<{ slide: SlideData; edit?: InlineEditCallbacks }> = ({ slide, edit }) => {
  const lines = toLines(slide.content);
  const subtitle = lines[0] || 'Синтетические данные (демо), Республика Беларусь';
  const editMode = !!(edit?.onTitleClick || edit?.onContentClick);

  return (
    <div className="relative w-full h-full bg-[#080d1a] overflow-hidden flex flex-col">
      {/* Animated gradient blobs */}
      <div className="absolute inset-0">
        <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-violet-600/10 rounded-full blur-[120px] -translate-x-1/2 -translate-y-1/2" />
        <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-[100px] translate-x-1/2 translate-y-1/2" />
      </div>
      <div className="absolute inset-0 opacity-[0.025]"
        style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)', backgroundSize: '48px 48px' }} />

      <div className="relative flex-shrink-0 h-1.5 bg-gradient-to-r from-violet-500 via-blue-500 to-purple-600" />

      <div className="relative flex-shrink-0 flex items-center justify-between px-10 pt-5 pb-2">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-violet-600/20 border border-violet-500/30 flex items-center justify-center">
            <BarChart2 className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <div className="text-xs font-bold text-white/80 tracking-widest uppercase">Prototip BI</div>
            <div className="text-[9px] text-slate-500 tracking-wider">Enterprise AI Analytics</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="px-3 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/25 text-[10px] text-emerald-400 font-medium">✓ AI-генерация</div>
          <div className="px-3 py-1 rounded-full bg-slate-800/60 border border-white/10 text-[10px] text-slate-400">{new Date().getFullYear()}</div>
        </div>
      </div>

      <div className="relative flex-1 flex flex-col justify-center px-10 pb-4 gap-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-violet-500/15 border border-violet-500/25">
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
            <span className="text-[11px] font-semibold text-violet-300 tracking-wider uppercase">BI-аналитика · Налоговые поступления РБ</span>
          </div>
        </div>

        <EditableZone label="Заголовок" onEdit={() => edit?.onTitleClick?.(slide.slide_idx)} editMode={editMode}>
          <h1 className="text-5xl font-black text-white leading-[1.1] max-w-3xl">
            <span className="bg-gradient-to-r from-white via-slate-100 to-slate-300 bg-clip-text text-transparent">
              {edit?.editingTitle ? edit.draftTitle : slide.title}
            </span>
          </h1>
        </EditableZone>

        <EditableZone label="Подзаголовок" onEdit={() => edit?.onContentClick?.(slide.slide_idx)} editMode={editMode}>
          <p className="text-base text-slate-400 max-w-xl leading-relaxed">
            {edit?.editingContent ? edit.draftContent?.split('\n')[0] : subtitle}
          </p>
        </EditableZone>

        <div className="flex gap-4 mt-2">
          {[
            { label: 'Регионов охвачено', value: '7', icon: MapPin, color: 'text-violet-400' },
            { label: 'Видов налогов', value: '12+', icon: FileText, color: 'text-blue-400' },
            { label: 'AI-агентов', value: '5', icon: Cpu, color: 'text-emerald-400' },
            { label: 'Инсайтов', value: '20+', icon: Lightbulb, color: 'text-amber-400' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="flex-1 bg-slate-900/60 backdrop-blur border border-white/8 rounded-xl p-3">
              <Icon className={`w-4 h-4 ${color} mb-1.5`} />
              <div className="text-2xl font-black text-white">{value}</div>
              <div className="text-[10px] text-slate-500 mt-0.5">{label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="relative flex-shrink-0 border-t border-white/5 bg-slate-950/40 px-10 py-3 flex items-center justify-between">
        <span className="text-[10px] text-slate-600">Prototip BI • AI Analytics Platform • Министерство по налогам и сборам РБ</span>
        <div className="flex items-center gap-2">
          <div className="w-1 h-1 rounded-full bg-violet-500" /><div className="w-1 h-1 rounded-full bg-blue-500" /><div className="w-1 h-1 rounded-full bg-emerald-500" />
        </div>
      </div>

      {/* Inline edit overlays */}
      <AnimatePresence>
        {edit?.editingTitle && (
          <InlineEditOverlay type="title" value={edit.draftTitle || slide.title} multiline={false}
            onSave={v => { edit.onDraftTitleChange?.(v); edit.onSave?.(); }}
            onCancel={() => edit.onCancel?.()} />
        )}
        {edit?.editingContent && (
          <InlineEditOverlay type="content" value={edit.draftContent || subtitle} multiline={true}
            onSave={v => { edit.onDraftContentChange?.(v); edit.onSave?.(); }}
            onCancel={() => edit.onCancel?.()} />
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── SUMMARY SLIDE ───────────────────────────────────────────────────────────
const SummarySlide: React.FC<{ slide: SlideData; edit?: InlineEditCallbacks }> = ({ slide, edit }) => {
  const text = Array.isArray(slide.content) ? slide.content.join(' ') : (slide.content || '');
  const displayText = edit?.editingContent ? (edit.draftContent || '') : text;
  const displayTitle = edit?.editingTitle ? (edit.draftTitle || '') : slide.title;
  const editMode = !!(edit?.onTitleClick || edit?.onContentClick);

  return (
    <div className="relative w-full h-full bg-[#080d1a] overflow-hidden flex flex-col">
      <div className="absolute top-0 right-0 w-[400px] h-[400px] bg-blue-600/8 rounded-full blur-[100px]" />
      <div className="relative flex-shrink-0 h-1 bg-gradient-to-r from-blue-500 via-violet-500 to-purple-600" />

      <div className="relative flex-1 flex flex-col px-10 py-5 gap-4 overflow-hidden">
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="px-2.5 py-1 rounded-md bg-blue-500/15 border border-blue-500/25 text-[10px] font-bold text-blue-400 tracking-widest uppercase">SUMMARY</div>
          <EditableZone label="Заголовок" onEdit={() => edit?.onTitleClick?.(slide.slide_idx)} editMode={editMode}>
            <h2 className="text-2xl font-black text-white">{displayTitle}</h2>
          </EditableZone>
        </div>

        <div className="flex-1 flex gap-5 overflow-hidden">
          <div className="flex-[3] flex flex-col gap-4">
            <div className="bg-slate-900/60 border border-white/8 rounded-xl p-5 flex-1">
              <div className="flex items-center gap-2 mb-3">
                <BookOpen className="w-4 h-4 text-blue-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Аналитический обзор</span>
              </div>
              <EditableZone label="Текст" onEdit={() => edit?.onContentClick?.(slide.slide_idx)} editMode={editMode}>
                <p className="text-sm text-slate-300 leading-relaxed">{displayText}</p>
              </EditableZone>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[{ label: 'Отчётный период', value: '2024 год', icon: FileText }, { label: 'Источник данных', value: 'ClickHouse OLAP', icon: Activity }]
                .map(({ label, value, icon: Icon }) => (
                  <div key={label} className="bg-slate-900/40 border border-white/6 rounded-xl p-4 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center flex-shrink-0">
                      <Icon className="w-4 h-4 text-slate-400" />
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">{label}</div>
                      <div className="text-sm font-bold text-white">{value}</div>
                    </div>
                  </div>
                ))}
            </div>
          </div>

          <div className="flex-[2] flex flex-col gap-3">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Ключевые параметры</div>
            {[
              { label: '7 регионов', desc: 'Охват', icon: MapPin, color: 'text-violet-400', bg: 'bg-violet-500/10 border-violet-500/20' },
              { label: 'Text-to-SQL', desc: 'Методология', icon: Cpu, color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20' },
              { label: '98.5%', desc: 'Точность', icon: Target, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
              { label: '5 агентов', desc: 'AI-система', icon: Activity, color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/20' },
            ].map(({ label, desc, icon: Icon, color, bg }) => (
              <div key={label} className={`border ${bg} rounded-xl p-3.5 flex items-center gap-3`}>
                <div className="w-9 h-9 rounded-lg bg-slate-900/60 flex items-center justify-center flex-shrink-0">
                  <Icon className={`w-5 h-5 ${color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] text-slate-500">{desc}</div>
                  <div className="text-sm font-bold text-white truncate">{label}</div>
                </div>
                <ChevronRight className="w-4 h-4 text-slate-600 flex-shrink-0" />
              </div>
            ))}
            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3.5 mt-auto">
              <div className="flex items-center gap-2 mb-1">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-emerald-300">Тренд</span>
              </div>
              <div className="text-[11px] text-slate-400">Рост налоговых поступлений в анализируемом периоде</div>
            </div>
          </div>
        </div>
      </div>

      <div className="relative flex-shrink-0 border-t border-white/5 bg-slate-950/40 px-10 py-2.5 flex items-center justify-between">
        <span className="text-[10px] text-slate-600">Prototip BI • AI Analytics Platform</span>
        <span className="text-[10px] text-slate-600">Слайд {slide.slide_idx + 1}</span>
      </div>

      <AnimatePresence>
        {edit?.editingTitle && (
          <InlineEditOverlay type="title" value={edit.draftTitle || slide.title} multiline={false}
            onSave={v => { edit.onDraftTitleChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
        {edit?.editingContent && (
          <InlineEditOverlay type="content" value={edit.draftContent || text} multiline={true}
            onSave={v => { edit.onDraftContentChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── THEMES SLIDE ────────────────────────────────────────────────────────────
const ThemesSlide: React.FC<{ slide: SlideData; edit?: InlineEditCallbacks }> = ({ slide, edit }) => {
  const themes = edit?.editingContent
    ? (edit.draftContent || '').split('\n').filter(Boolean)
    : toLines(slide.content);
  const displayTitle = edit?.editingTitle ? (edit.draftTitle || '') : slide.title;
  const editMode = !!(edit?.onTitleClick || edit?.onContentClick);

  return (
    <div className="relative w-full h-full bg-[#080d1a] overflow-hidden flex flex-col">
      <div className="absolute top-0 left-1/2 w-[500px] h-[300px] bg-violet-600/8 rounded-full blur-[100px] -translate-x-1/2 -translate-y-1/2" />
      <div className="relative flex-shrink-0 h-1 bg-gradient-to-r from-violet-500 via-blue-500 to-cyan-500" />

      <div className="relative flex-1 flex flex-col px-10 py-5 gap-4 overflow-hidden">
        <div className="flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="px-2.5 py-1 rounded-md bg-violet-500/15 border border-violet-500/25 text-[10px] font-bold text-violet-400 tracking-widest uppercase">AGENDA</div>
            <EditableZone label="Заголовок" onEdit={() => edit?.onTitleClick?.(slide.slide_idx)} editMode={editMode}>
              <h2 className="text-2xl font-black text-white">{displayTitle}</h2>
            </EditableZone>
          </div>
          <div className="text-xs text-slate-500">{themes.length} разделов</div>
        </div>

        <EditableZone label="Темы (каждая строка — тема)" onEdit={() => edit?.onContentClick?.(slide.slide_idx)} editMode={editMode}>
          <div className="flex-1 flex flex-col gap-2.5 overflow-hidden">
            {themes.map((theme, i) => {
              const colors = THEME_COLORS[i % THEME_COLORS.length];
              const Icon = THEME_ICONS[i % THEME_ICONS.length];
              return (
                <div key={i} className={`bg-gradient-to-r ${colors.bg} border ${colors.border} rounded-xl p-4 flex items-center gap-4`}>
                  <div className="w-10 h-10 rounded-xl bg-slate-900/60 flex items-center justify-center flex-shrink-0">
                    <Icon className={`w-5 h-5 ${colors.icon}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] text-slate-500 mb-0.5">Раздел {i + 1}</div>
                    <div className="text-sm font-semibold text-white leading-snug">{theme}</div>
                  </div>
                  <div className={`px-2 py-1 rounded-md ${colors.badge} text-[10px] font-bold flex-shrink-0`}>0{i + 1}</div>
                </div>
              );
            })}
          </div>
        </EditableZone>

        <div className="flex-shrink-0 grid grid-cols-3 gap-3">
          {[{ label: 'Методология', desc: 'AI Text-to-SQL + BI', icon: Cpu }, { label: 'Источник', desc: 'ClickHouse OLAP', icon: Activity }, { label: 'Охват', desc: 'Все регионы РБ', icon: Globe }]
            .map(({ label, desc, icon: Icon }) => (
              <div key={label} className="bg-slate-900/50 border border-white/6 rounded-xl p-3 flex items-center gap-2">
                <Icon className="w-4 h-4 text-slate-500 flex-shrink-0" />
                <div>
                  <div className="text-[10px] text-slate-500">{label}</div>
                  <div className="text-xs font-semibold text-slate-300">{desc}</div>
                </div>
              </div>
            ))}
        </div>
      </div>

      <div className="relative flex-shrink-0 border-t border-white/5 bg-slate-950/40 px-10 py-2.5 flex items-center justify-between">
        <span className="text-[10px] text-slate-600">Prototip BI • AI Analytics Platform</span>
        <span className="text-[10px] text-slate-600">Слайд {slide.slide_idx + 1}</span>
      </div>

      <AnimatePresence>
        {edit?.editingTitle && (
          <InlineEditOverlay type="title" value={edit.draftTitle || slide.title} multiline={false}
            onSave={v => { edit.onDraftTitleChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
        {edit?.editingContent && (
          <InlineEditOverlay type="content" value={edit.draftContent || toLines(slide.content).join('\n')} multiline={true}
            onSave={v => { edit.onDraftContentChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── CHART SLIDE ─────────────────────────────────────────────────────────────
const ChartSlide: React.FC<{ slide: SlideData; pngUrl?: string; edit?: InlineEditCallbacks; showChartPicker?: boolean }> = ({
  slide, pngUrl, edit, showChartPicker
}) => {
  const conclusion = Array.isArray(slide.content) ? slide.content.join(' ') : (slide.content || '');
  const displayTitle = edit?.editingTitle ? (edit.draftTitle || '') : slide.title;
  const editMode = !!(edit?.onTitleClick || edit?.onContentClick);

  return (
    <div className="relative w-full h-full bg-[#080d1a] overflow-hidden flex flex-col">
      <div className="absolute top-0 right-0 w-[400px] h-[300px] bg-blue-600/6 rounded-full blur-[100px]" />
      <div className="relative flex-shrink-0 h-1 bg-gradient-to-r from-emerald-500 via-blue-500 to-violet-500" />

      <div className="relative flex-1 flex flex-col px-8 py-4 gap-3 overflow-hidden">
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="px-2.5 py-1 rounded-md bg-emerald-500/15 border border-emerald-500/25 text-[10px] font-bold text-emerald-400 tracking-widest uppercase">DATA</div>
          <EditableZone label="Заголовок" onEdit={() => edit?.onTitleClick?.(slide.slide_idx)} editMode={editMode}>
            <h2 className="text-xl font-black text-white flex-1 min-w-0">{displayTitle}</h2>
          </EditableZone>
        </div>

        <div className="flex-1 flex gap-4 overflow-hidden min-h-0">
          <div className="flex-[3] bg-white rounded-xl overflow-hidden flex items-center justify-center">
            {pngUrl ? (
              <img src={pngUrl} alt={slide.title} className="w-full h-full object-contain" onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }} />
            ) : (
              <div className="flex flex-col items-center gap-3 text-slate-400 p-8">
                <BarChart2 className="w-12 h-12 text-slate-300" />
                <span className="text-sm text-slate-500">График генерируется...</span>
              </div>
            )}
          </div>

          <div className="flex-[2] flex flex-col gap-3 overflow-hidden">
            <EditableZone label="Вывод" onEdit={() => edit?.onContentClick?.(slide.slide_idx)} editMode={editMode}>
              {conclusion && (
                <div className="bg-slate-900/70 border border-white/8 rounded-xl p-4 flex-shrink-0">
                  <div className="flex items-center gap-2 mb-2">
                    <Lightbulb className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Ключевой вывод</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed line-clamp-5">{conclusion}</p>
                </div>
              )}
            </EditableZone>

            {[
              { label: 'Тренд', value: '↑ Рост', icon: TrendingUp, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
              { label: 'Аномалии', value: 'Выявлены', icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/20' },
              { label: 'Достоверность', value: 'Высокая', icon: CheckCircle2, color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20' },
            ].map(({ label, value, icon: Icon, color, bg }) => (
              <div key={label} className={`border ${bg} rounded-xl p-3 flex items-center gap-2 flex-shrink-0`}>
                <Icon className={`w-4 h-4 ${color} flex-shrink-0`} />
                <div className="flex-1">
                  <div className="text-[9px] text-slate-500">{label}</div>
                  <div className="text-xs font-bold text-white">{value}</div>
                </div>
              </div>
            ))}

            <div className="mt-auto bg-slate-900/40 border border-white/5 rounded-xl p-3">
              <div className="text-[9px] text-slate-600">Источник данных</div>
              <div className="text-[11px] text-slate-400 font-medium">Министерство по налогам и сборам РБ</div>
            </div>
          </div>
        </div>
      </div>

      <div className="relative flex-shrink-0 border-t border-white/5 bg-slate-950/40 px-8 py-2.5 flex items-center justify-between">
        <span className="text-[10px] text-slate-600">Prototip BI • AI Analytics Platform</span>
        <span className="text-[10px] text-slate-600">Слайд {slide.slide_idx + 1}</span>
      </div>

      {showChartPicker && edit?.onChartTypeChange && (
        <ChartTypeSelector current={edit.chartType} onChange={edit.onChartTypeChange} isUpdating={edit.isUpdating} />
      )}

      <AnimatePresence>
        {edit?.editingTitle && (
          <InlineEditOverlay type="title" value={edit.draftTitle || slide.title} multiline={false}
            onSave={v => { edit.onDraftTitleChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
        {edit?.editingContent && (
          <InlineEditOverlay type="content" value={edit.draftContent || conclusion} multiline={true}
            onSave={v => { edit.onDraftContentChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── TAKEAWAYS SLIDE ─────────────────────────────────────────────────────────
const TakeawaysSlide: React.FC<{ slide: SlideData; edit?: InlineEditCallbacks }> = ({ slide, edit }) => {
  const takeaways = edit?.editingContent
    ? (edit.draftContent || '').split('\n').filter(Boolean)
    : toLines(slide.content);
  const displayTitle = edit?.editingTitle ? (edit.draftTitle || '') : slide.title;
  const editMode = !!(edit?.onTitleClick || edit?.onContentClick);

  // Show first 10 takeaways in 2-col grid if many
  const shown = takeaways.slice(0, 10);
  const useGrid = shown.length > 5;

  return (
    <div className="relative w-full h-full bg-[#080d1a] overflow-hidden flex flex-col">
      <div className="absolute bottom-0 right-0 w-[400px] h-[400px] bg-emerald-600/6 rounded-full blur-[100px]" />
      <div className="relative flex-shrink-0 h-1 bg-gradient-to-r from-emerald-400 via-teal-500 to-cyan-600" />

      <div className="relative flex-1 flex flex-col px-10 py-4 gap-3 overflow-hidden">
        <div className="flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="px-2.5 py-1 rounded-md bg-emerald-500/15 border border-emerald-500/25 text-[10px] font-bold text-emerald-400 tracking-widest uppercase">KEY INSIGHTS</div>
            <EditableZone label="Заголовок" onEdit={() => edit?.onTitleClick?.(slide.slide_idx)} editMode={editMode}>
              <h2 className="text-2xl font-black text-white">{displayTitle}</h2>
            </EditableZone>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-emerald-400 font-semibold">{shown.length}</span>
            <span className="text-[10px] text-slate-500">ключевых вывода</span>
          </div>
        </div>

        <EditableZone label="Выводы (каждая строка — пункт)" onEdit={() => edit?.onContentClick?.(slide.slide_idx)} editMode={editMode}>
          <div className={`flex-1 ${useGrid ? 'grid grid-cols-2' : 'flex flex-col'} gap-2 overflow-hidden`}>
            {shown.map((t, i) => {
              const c = THEME_COLORS[i % THEME_COLORS.length];
              const pct = Math.max(45, 100 - i * 6);
              return (
                <div key={i} className="flex items-start gap-2.5 bg-slate-900/50 border border-white/6 rounded-xl p-3">
                  <div className={`w-6 h-6 ${c.bar} rounded-lg flex items-center justify-center flex-shrink-0 text-[10px] font-black text-white mt-0.5`}>{i + 1}</div>
                  <div className="flex-1 min-w-0">
                    <p className={`${useGrid ? 'text-xs' : 'text-sm'} text-slate-200 leading-snug line-clamp-3`}>{t}</p>
                    <div className="mt-1.5 h-0.5 bg-slate-800 rounded-full overflow-hidden">
                      <div className={`h-full ${c.bar} rounded-full`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </EditableZone>

        <div className="flex-shrink-0 bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3 flex items-center gap-3">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <p className="text-xs text-slate-400 flex-1">
            {takeaways.length} выводов сформированы на основе AI-анализа налоговых данных Республики Беларусь (синтетический датасет)
          </p>
        </div>
      </div>

      <div className="relative flex-shrink-0 border-t border-white/5 bg-slate-950/40 px-10 py-2.5 flex items-center justify-between">
        <span className="text-[10px] text-slate-600">Prototip BI • AI Analytics Platform</span>
        <span className="text-[10px] text-slate-600">Слайд {slide.slide_idx + 1}</span>
      </div>

      <AnimatePresence>
        {edit?.editingTitle && (
          <InlineEditOverlay type="title" value={edit.draftTitle || slide.title} multiline={false}
            onSave={v => { edit.onDraftTitleChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
        {edit?.editingContent && (
          <InlineEditOverlay type="content" value={edit.draftContent || toLines(slide.content).join('\n')} multiline={true}
            onSave={v => { edit.onDraftContentChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── RECOMMENDATIONS SLIDE ────────────────────────────────────────────────────
const RecommendationsSlide: React.FC<{ slide: SlideData; edit?: InlineEditCallbacks }> = ({ slide, edit }) => {
  const recs = edit?.editingContent
    ? (edit.draftContent || '').split('\n').filter(Boolean)
    : toLines(slide.content);
  const displayTitle = edit?.editingTitle ? (edit.draftTitle || '') : slide.title;
  const editMode = !!(edit?.onTitleClick || edit?.onContentClick);

  const REC_COLORS_FULL = [
    { bg: 'bg-violet-600/15', border: 'border-violet-500/25', icon: 'text-violet-400', num: 'bg-violet-600', bar: 'bg-violet-500' },
    { bg: 'bg-blue-600/15', border: 'border-blue-500/25', icon: 'text-blue-400', num: 'bg-blue-600', bar: 'bg-blue-500' },
    { bg: 'bg-emerald-600/15', border: 'border-emerald-500/25', icon: 'text-emerald-400', num: 'bg-emerald-600', bar: 'bg-emerald-500' },
    { bg: 'bg-amber-600/15', border: 'border-amber-500/25', icon: 'text-amber-400', num: 'bg-amber-600', bar: 'bg-amber-500' },
  ];

  return (
    <div className="relative w-full h-full bg-[#080d1a] overflow-hidden flex flex-col">
      <div className="absolute top-0 right-0 w-[400px] h-[300px] bg-amber-600/6 rounded-full blur-[100px]" />
      <div className="relative flex-shrink-0 h-1 bg-gradient-to-r from-amber-400 via-orange-500 to-rose-500" />

      <div className="relative flex-1 flex flex-col px-10 py-5 gap-4 overflow-hidden">
        <div className="flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="px-2.5 py-1 rounded-md bg-amber-500/15 border border-amber-500/25 text-[10px] font-bold text-amber-400 tracking-widest uppercase">ACTIONS</div>
            <EditableZone label="Заголовок" onEdit={() => edit?.onTitleClick?.(slide.slide_idx)} editMode={editMode}>
              <h2 className="text-2xl font-black text-white">{displayTitle}</h2>
            </EditableZone>
          </div>
          <div className="px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-[10px] font-semibold text-amber-400">
            {recs.length} рекомендаций
          </div>
        </div>

        <EditableZone label="Рекомендации (каждая строка — пункт)" onEdit={() => edit?.onContentClick?.(slide.slide_idx)} editMode={editMode}>
          <div className="flex-1 grid grid-cols-2 gap-3 overflow-hidden">
            {recs.slice(0, 4).map((rec, i) => {
              const c = REC_COLORS_FULL[i % REC_COLORS_FULL.length];
              const Icon = REC_ICONS[i % REC_ICONS.length];
              return (
                <div key={i} className={`${c.bg} border ${c.border} rounded-xl p-4 flex flex-col gap-3`}>
                  <div className="flex items-center justify-between">
                    <div className={`w-8 h-8 ${c.num} rounded-lg flex items-center justify-center`}>
                      <Icon className="w-4 h-4 text-white" />
                    </div>
                    <span className="text-[10px] text-slate-500 font-bold">ПРИОРИТЕТ {i + 1}</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed flex-1">{rec}</p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1 bg-slate-800 rounded-full overflow-hidden">
                      <div className={`h-full ${c.bar} rounded-full`} style={{ width: `${90 - i * 15}%` }} />
                    </div>
                    <span className={`text-[10px] font-bold ${c.icon}`}>{90 - i * 15}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </EditableZone>

        <div className="flex-shrink-0 bg-slate-900/60 border border-white/8 rounded-xl p-3 flex items-center gap-3">
          <Shield className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <p className="text-[11px] text-slate-400">Рекомендации сформированы AI-системой. Требуют экспертной валидации перед внедрением.</p>
        </div>
      </div>

      <div className="relative flex-shrink-0 border-t border-white/5 bg-slate-950/40 px-10 py-2.5 flex items-center justify-between">
        <span className="text-[10px] text-slate-600">Prototip BI • AI Analytics Platform</span>
        <span className="text-[10px] text-slate-600">Слайд {slide.slide_idx + 1}</span>
      </div>

      <AnimatePresence>
        {edit?.editingTitle && (
          <InlineEditOverlay type="title" value={edit.draftTitle || slide.title} multiline={false}
            onSave={v => { edit.onDraftTitleChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
        {edit?.editingContent && (
          <InlineEditOverlay type="content" value={edit.draftContent || toLines(slide.content).join('\n')} multiline={true}
            onSave={v => { edit.onDraftContentChange?.(v); edit.onSave?.(); }} onCancel={() => edit.onCancel?.()} />
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── Main Renderer ────────────────────────────────────────────────────────────
export interface SlideRendererProps {
  slide: SlideData;
  pngUrl?: string | null;
  edit?: InlineEditCallbacks;
  showChartPicker?: boolean;
}

export const SlideRenderer: React.FC<SlideRendererProps> = ({ slide, pngUrl, edit, showChartPicker }) => {
  switch (slide.slide_type) {
    case 'title':           return <TitleSlide slide={slide} edit={edit} />;
    case 'summary':         return <SummarySlide slide={slide} edit={edit} />;
    case 'themes':          return <ThemesSlide slide={slide} edit={edit} />;
    case 'chart':           return <ChartSlide slide={slide} pngUrl={pngUrl ?? undefined} edit={edit} showChartPicker={showChartPicker} />;
    case 'takeaways':       return <TakeawaysSlide slide={slide} edit={edit} />;
    case 'recommendations': return <RecommendationsSlide slide={slide} edit={edit} />;
    default:
      if (pngUrl) {
        return <div className="w-full h-full bg-slate-950 flex items-center justify-center">
          <img src={pngUrl} alt={slide.title} className="max-w-full max-h-full object-contain" />
        </div>;
      }
      return <div className="w-full h-full bg-[#080d1a] flex flex-col items-center justify-center gap-3">
        <FileText className="w-12 h-12 text-slate-600" />
        <p className="text-slate-400 font-medium">{slide.title}</p>
      </div>;
  }
};

// ─── Thumbnail Renderer ───────────────────────────────────────────────────────
export const SlideThumbnail: React.FC<{
  slide: SlideData; pngUrl?: string | null; isActive: boolean; index: number; onClick: () => void;
}> = ({ slide, pngUrl, isActive, index, onClick }) => (
  <motion.div
    whileHover={{ scale: 1.04, y: -2 }}
    onClick={onClick}
    className={`cursor-pointer rounded-xl overflow-hidden border-2 transition-all duration-200 flex-shrink-0 ${
      isActive ? 'border-violet-500 shadow-lg shadow-violet-500/25' : 'border-white/5 hover:border-white/20'
    }`}
  >
    <div className="w-full aspect-[16/9] overflow-hidden relative">
      <div className="absolute inset-0" style={{ transform: 'scale(0.18)', transformOrigin: 'top left', width: '556%', height: '556%' }}>
        <SlideRenderer slide={slide} pngUrl={pngUrl} />
      </div>
    </div>
    <div className={`px-2 py-1.5 ${isActive ? 'bg-violet-600/20' : 'bg-slate-900/80'} transition-colors`}>
      <span className="text-[10px] text-slate-400 font-medium">#{index + 1}</span>
    </div>
  </motion.div>
);
