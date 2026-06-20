import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Presentation, Download, Trash2, ChevronLeft, ChevronRight,
  Monitor, LayoutGrid, FileText, Calendar, Layers,
  Sparkles, Info, Pencil, Check, X as XIcon, RefreshCw, Save,
  Loader2, Maximize2, Minimize2, List, BarChart2
} from 'lucide-react';
import { useChatStore, PresentationHistoryItem } from '../../store/useChatStore';
import { Button } from '../ui/button';
import { SlideRenderer, SlideThumbnail, SlideData, toLines } from './SlideRenderer';

const API = 'http://localhost:8000';

function getSlideUrl(pngPaths: string[], i: number): string | null {
  const path = pngPaths?.[i];
  if (!path) return null;
  return `${API}/api/v1/download?file=${encodeURIComponent(path)}&inline=true`;
}

// ─── Inline editing state ────────────────────────────────────────────────────
interface EditState {
  slideIdx: number;
  field: 'title' | 'content' | null;
  draftTitle: string;
  draftContent: string;
  chartType?: string;
}

// ─── Slide Viewer ─────────────────────────────────────────────────────────────
const SlideViewer: React.FC<{
  presentation: PresentationHistoryItem;
  activeSlide: number;
  onSlideChange: (i: number) => void;
}> = ({ presentation, activeSlide, onSlideChange }) => {
  const total = presentation.num_slides;
  const slides: SlideData[] = presentation.slides || [];
  const pngPaths = presentation.slide_png_paths || [];

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [successFlash, setSuccessFlash] = useState(false);

  // Edit state
  const [editState, setEditState] = useState<EditState | null>(null);

  const slideData: SlideData | undefined = useMemo(
    () => slides.find(s => s.slide_idx === activeSlide),
    [slides, activeSlide]
  );

  // Reset edit when changing slides
  useEffect(() => { setEditState(null); }, [activeSlide]);

  // Keyboard nav
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (editState?.field) return; // Don't nav while editing
      if (e.key === 'ArrowLeft') onSlideChange(Math.max(0, activeSlide - 1));
      if (e.key === 'ArrowRight') onSlideChange(Math.min(total - 1, activeSlide + 1));
      if (e.key === 'Escape') setIsFullscreen(false);
      if (e.key === 'f' || e.key === 'F') setIsFullscreen(f => !f);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [activeSlide, total, onSlideChange, editState]);

  // Initialize edit state when entering edit for a slide
  const startEdit = useCallback((slideIdx: number, field: 'title' | 'content') => {
    const s = slides.find(sd => sd.slide_idx === slideIdx);
    if (!s) return;
    setEditState({
      slideIdx,
      field,
      draftTitle: s.title,
      draftContent: Array.isArray(s.content) ? s.content.join('\n') : (s.content || ''),
      chartType: undefined,
    });
  }, [slides]);

  const cancelEdit = useCallback(() => setEditState(null), []);

  // Save text edit to backend
  const saveEdit = useCallback(async () => {
    if (!editState || !slideData || !presentation.id) return;
    setIsUpdating(true);
    try {
      const isListType = ['themes', 'takeaways', 'recommendations'].includes(slideData.slide_type);
      const contentPayload = isListType
        ? editState.draftContent.split('\n').filter(s => s.trim().length > 0)
        : editState.draftContent;

      const res = await fetch(`${API}/api/v1/presentation/update`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
        },
        body: JSON.stringify({
          presentation_id: presentation.id,
          slide_updates: {
            [activeSlide]: {
              title: editState.draftTitle,
              content: contentPayload
            }
          }
        })
      });
      if (!res.ok) throw new Error('Update failed');
      const updatedPres = await res.json();
      useChatStore.getState().updatePresentation(presentation.id, updatedPres);
      setEditState(null);
      setSuccessFlash(true);
      setTimeout(() => setSuccessFlash(false), 1500);
    } catch (e) {
      console.error(e);
      alert('Ошибка при сохранении');
    } finally {
      setIsUpdating(false);
    }
  }, [editState, slideData, presentation.id, activeSlide]);

  // Change chart type
  const handleChartTypeChange = useCallback(async (newType: string) => {
    if (!presentation.id || !slideData) return;
    setIsUpdating(true);
    try {
      const res = await fetch(`${API}/api/v1/presentation/update`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
        },
        body: JSON.stringify({
          presentation_id: presentation.id,
          slide_updates: {
            [activeSlide]: {
              title: slideData.title,
              content: slideData.content,
              chart_type: newType,
            }
          }
        })
      });
      if (!res.ok) throw new Error('Chart type update failed');
      const updatedPres = await res.json();
      useChatStore.getState().updatePresentation(presentation.id, updatedPres);
      setSuccessFlash(true);
      setTimeout(() => setSuccessFlash(false), 1500);
    } catch (e) {
      console.error(e);
    } finally {
      setIsUpdating(false);
    }
  }, [presentation.id, slideData, activeSlide]);

  const currentPngUrl = getSlideUrl(pngPaths, activeSlide);
  const isChartSlide = slideData?.slide_type === 'chart';

  // Build edit callbacks
  const editCallbacks = useMemo(() => {
    if (!slideData) return undefined;
    return {
      onTitleClick: (idx: number) => startEdit(idx, 'title'),
      onContentClick: (idx: number) => startEdit(idx, 'content'),
      editingTitle: editState?.slideIdx === activeSlide && editState.field === 'title',
      editingContent: editState?.slideIdx === activeSlide && editState.field === 'content',
      draftTitle: editState?.draftTitle ?? slideData.title,
      draftContent: editState?.draftContent ?? (Array.isArray(slideData.content) ? slideData.content.join('\n') : (slideData.content || '')),
      onDraftTitleChange: (v: string) => setEditState(prev => prev ? { ...prev, draftTitle: v } : null),
      onDraftContentChange: (v: string) => setEditState(prev => prev ? { ...prev, draftContent: v } : null),
      onSave: saveEdit,
      onCancel: cancelEdit,
      isUpdating,
      chartType: editState?.chartType,
      onChartTypeChange: handleChartTypeChange,
    };
  }, [slideData, editState, activeSlide, startEdit, saveEdit, cancelEdit, isUpdating, handleChartTypeChange]);

  const currentSlide: SlideData = slideData || {
    slide_idx: activeSlide,
    slide_type: 'chart',
    title: `Слайд ${activeSlide + 1}`,
    content: null,
  };

  const slideArea = (
    <div className="relative flex-1 overflow-hidden bg-[#080d1a]">
      <AnimatePresence mode="wait">
        <motion.div
          key={activeSlide}
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -30 }}
          transition={{ duration: 0.18, ease: 'easeInOut' }}
          className="absolute inset-0"
        >
          <SlideRenderer
            slide={currentSlide}
            pngUrl={currentPngUrl}
            edit={slides.length > 0 ? editCallbacks : undefined}
            showChartPicker={isChartSlide && !editState?.field}
          />
        </motion.div>
      </AnimatePresence>

      {/* Success flash */}
      <AnimatePresence>
        {successFlash && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute top-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 bg-emerald-600 text-white text-sm font-semibold px-4 py-2 rounded-xl shadow-lg"
          >
            <Check className="w-4 h-4" /> Сохранено
          </motion.div>
        )}
      </AnimatePresence>

      {/* Nav arrows */}
      {!editState?.field && (
        <>
          <button onClick={() => onSlideChange(Math.max(0, activeSlide - 1))} disabled={activeSlide === 0}
            className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-slate-900/80 backdrop-blur border border-white/10 flex items-center justify-center text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-0 transition-all shadow-lg z-10">
            <ChevronLeft className="w-5 h-5" />
          </button>
          <button onClick={() => onSlideChange(Math.min(total - 1, activeSlide + 1))} disabled={activeSlide >= total - 1}
            className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-slate-900/80 backdrop-blur border border-white/10 flex items-center justify-center text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-0 transition-all shadow-lg z-10">
            <ChevronRight className="w-5 h-5" />
          </button>
        </>
      )}

      {/* Top controls */}
      {!editState?.field && (
        <div className="absolute top-3 right-3 flex items-center gap-2 z-10">
          {/* Edit mode hint */}
          {slides.length > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900/80 backdrop-blur border border-white/10 text-[11px] text-slate-400 shadow-lg">
              <Pencil className="w-3 h-3 text-violet-400" />
              Кликни на текст для редактирования
            </div>
          )}
          <button onClick={() => setIsFullscreen(!isFullscreen)}
            className="w-8 h-8 rounded-lg bg-slate-900/80 backdrop-blur border border-white/10 flex items-center justify-center text-slate-400 hover:text-white transition-all shadow-lg">
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      )}

      {/* Slide counter */}
      {!editState?.field && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-slate-900/80 backdrop-blur border border-white/10 rounded-full px-4 py-1.5 text-xs font-semibold text-slate-300 z-10">
          {activeSlide + 1} / {total}
          <span className="ml-2 text-slate-600 text-[10px]">← → для навигации</span>
        </div>
      )}

      {/* Loader overlay while updating */}
      {isUpdating && !editState?.field && (
        <div className="absolute inset-0 z-20 bg-slate-950/50 flex items-center justify-center">
          <div className="flex items-center gap-3 bg-slate-900 border border-white/10 rounded-xl px-5 py-3 shadow-xl">
            <Loader2 className="w-5 h-5 text-violet-400 animate-spin" />
            <span className="text-sm text-slate-300">Применяем изменения...</span>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Main slide area */}
      <div className={`${isFullscreen ? 'fixed inset-0 z-[200] bg-black' : 'relative flex-1 min-h-0 rounded-2xl overflow-hidden border border-white/8'} flex flex-col`}>
        {slideArea}
        {isFullscreen && (
          <button onClick={() => setIsFullscreen(false)}
            className="absolute top-4 right-4 z-50 w-10 h-10 rounded-full bg-slate-900/80 border border-white/10 flex items-center justify-center text-slate-300 hover:text-white">
            <Minimize2 className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Thumbnails */}
      {!isFullscreen && slides.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar flex-shrink-0" style={{ minHeight: '90px' }}>
          {slides.map((s, i) => (
            <div key={i} className="flex-shrink-0 w-28">
              <SlideThumbnail
                slide={s}
                pngUrl={getSlideUrl(pngPaths, i)}
                isActive={i === activeSlide}
                index={i}
                onClick={() => onSlideChange(i)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Outline View ─────────────────────────────────────────────────────────────
const OutlineView: React.FC<{
  presentation: PresentationHistoryItem;
  onSlideClick: (i: number) => void;
}> = ({ presentation, onSlideClick }) => {
  const slides: SlideData[] = presentation.slides || [];
  const TYPE_META: Record<string, { label: string; color: string; bg: string }> = {
    title: { label: 'TITLE', color: 'text-violet-400', bg: 'bg-violet-500/15 border-violet-500/25' },
    summary: { label: 'OVERVIEW', color: 'text-blue-400', bg: 'bg-blue-500/15 border-blue-500/25' },
    themes: { label: 'AGENDA', color: 'text-cyan-400', bg: 'bg-cyan-500/15 border-cyan-500/25' },
    chart: { label: 'DATA', color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/25' },
    takeaways: { label: 'INSIGHTS', color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/25' },
    recommendations: { label: 'ACTIONS', color: 'text-rose-400', bg: 'bg-rose-500/15 border-rose-500/25' },
    appendix: { label: 'APPENDIX', color: 'text-slate-400', bg: 'bg-slate-700/30 border-slate-600/20' },
  };
  return (
    <div className="h-full overflow-y-auto custom-scrollbar space-y-2 pr-1">
      {slides.map((s, i) => {
        const meta = TYPE_META[s.slide_type] || { label: s.slide_type.toUpperCase(), color: 'text-slate-400', bg: 'bg-slate-800' };
        const lines = toLines(s.content);
        return (
          <motion.div key={i} whileHover={{ x: 4 }} onClick={() => onSlideClick(i)}
            className="cursor-pointer bg-slate-900/60 border border-white/6 rounded-xl p-4 hover:border-violet-500/30 transition-all">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-lg font-black text-slate-700 w-8 flex-shrink-0">{String(i + 1).padStart(2, '0')}</span>
              <span className={`px-2 py-0.5 rounded border text-[9px] font-bold tracking-widest ${meta.bg} ${meta.color}`}>{meta.label}</span>
              <h3 className="text-sm font-bold text-white flex-1 min-w-0 truncate">{s.title}</h3>
            </div>
            {lines.slice(0, 2).map((line, li) => (
              <p key={li} className="text-xs text-slate-500 ml-11 leading-relaxed truncate">• {line}</p>
            ))}
            {lines.length > 2 && <p className="text-[10px] text-slate-600 ml-11 mt-1">+{lines.length - 2} ещё...</p>}
          </motion.div>
        );
      })}
    </div>
  );
};

// ─── Editable Title ──────────────────────────────────────────────────────────
const EditableTitle: React.FC<{ value: string; onSave: (val: string) => void }> = ({ value, onSave }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const commit = () => { if (draft.trim()) onSave(draft.trim()); setEditing(false); };
  if (editing) return (
    <div className="flex items-center gap-2 flex-1 min-w-0">
      <input autoFocus value={draft} onChange={e => setDraft(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { setDraft(value); setEditing(false); } }}
        className="flex-1 bg-slate-800 border border-violet-500/40 rounded-lg px-3 py-1 text-sm text-white outline-none focus:border-violet-500" />
      <button onClick={commit} className="w-7 h-7 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center"><Check className="w-3.5 h-3.5" /></button>
      <button onClick={() => { setDraft(value); setEditing(false); }} className="w-7 h-7 rounded-lg bg-rose-500/10 text-rose-400 flex items-center justify-center"><XIcon className="w-3.5 h-3.5" /></button>
    </div>
  );
  return (
    <div className="flex items-center gap-2 flex-1 min-w-0">
      <h2 className="text-base font-bold text-white truncate">{value}</h2>
      <button onClick={() => { setDraft(value); setEditing(true); }}
        className="flex-shrink-0 w-6 h-6 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-700 flex items-center justify-center">
        <Pencil className="w-3 h-3" />
      </button>
    </div>
  );
};

// ─── Main View ────────────────────────────────────────────────────────────────
interface PresentationViewProps {
  onBackToChat?: () => void;
  token?: string | null;
}

export const PresentationView: React.FC<PresentationViewProps> = ({ onBackToChat }) => {
  const presentationHistory = useChatStore(s => s.presentationHistory);
  const activePresentationId = useChatStore(s => s.activePresentationId);
  const deletePresentation = useChatStore(s => s.deletePresentation);
  const updatePresentation = useChatStore(s => s.updatePresentation);

  const [activeSlide, setActiveSlide] = useState(0);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [viewMode, setViewMode] = useState<'slides' | 'outline' | 'info'>('slides');

  const activePresentation = useMemo(
    () => presentationHistory.find(p => p.id === activePresentationId) ?? null,
    [presentationHistory, activePresentationId]
  );

  useEffect(() => { setActiveSlide(0); setViewMode('slides'); }, [activePresentationId]);

  const handleRenameTitle = useCallback((newTitle: string) => {
    if (!activePresentation) return;
    updatePresentation(activePresentation.id, { title: newTitle });
  }, [activePresentation, updatePresentation]);

  const handleDownload = useCallback(() => {
    if (!activePresentation) return;
    const link = document.createElement('a');
    link.href = `${API}/api/v1/download?file=${encodeURIComponent(activePresentation.pptx_path)}`;
    link.download = activePresentation.pptx_path.split('/').pop() || 'presentation.pptx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [activePresentation]);

  const handleDelete = useCallback(() => {
    if (!activePresentationId) return;
    deletePresentation(activePresentationId);
    setShowDeleteConfirm(false);
    if (presentationHistory.length <= 1 && onBackToChat) onBackToChat();
  }, [activePresentationId, deletePresentation, presentationHistory.length, onBackToChat]);

  // ─── Empty state ─────────────────────────────────────────────────────────
  if (presentationHistory.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 text-center p-8">
        <div className="w-24 h-24 rounded-3xl bg-violet-600/10 border border-violet-500/20 flex items-center justify-center">
          <Presentation className="w-12 h-12 text-violet-400" />
        </div>
        <div>
          <h3 className="text-xl font-bold text-white mb-2">Нет презентаций</h3>
          <p className="text-slate-400 text-sm max-w-xs">Сгенерируйте первую презентацию через «Сгенерировать Презентацию»</p>
        </div>
        {onBackToChat && <Button onClick={onBackToChat} variant="outline" className="border-white/10 text-slate-300">← Вернуться к чату</Button>}
      </div>
    );
  }

  return (
    <div className="flex h-full gap-4">
      <div className="flex-1 min-w-0 flex flex-col gap-3 overflow-hidden">
        {activePresentation ? (
          <>
            {/* Toolbar */}
            <div className="premium-glass rounded-2xl border border-white/8 p-3 flex items-center gap-3 flex-shrink-0">
              <Button onClick={onBackToChat ?? (() => {})} variant="ghost" size="icon" className="w-9 h-9 rounded-xl text-slate-400 hover:text-white hover:bg-white/10" title="Закрыть">
                <XIcon className="w-5 h-5" />
              </Button>
              <div className="w-9 h-9 rounded-xl bg-violet-600/15 border border-violet-500/20 flex items-center justify-center flex-shrink-0">
                <Presentation className="w-4 h-4 text-violet-400" />
              </div>
              <div className="flex-1 min-w-0">
                <EditableTitle value={activePresentation.title} onSave={handleRenameTitle} />
                <div className="flex items-center gap-3 text-[10px] text-slate-500 mt-0.5">
                  <span className="flex items-center gap-1"><Layers className="w-3 h-3" /> {activePresentation.num_slides} слайдов</span>
                  <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> {new Date(activePresentation.timestamp).toLocaleDateString('ru-RU')}</span>
                  <span className="flex items-center gap-1 text-violet-400">
                    <Pencil className="w-3 h-3" /> Клик на текст = редактировать
                  </span>
                </div>
              </div>

              {/* View mode */}
              <div className="flex items-center gap-1 bg-slate-800/60 rounded-lg p-1">
                {([
                  { id: 'slides', icon: Monitor, label: 'Слайды' },
                  { id: 'outline', icon: List, label: 'Структура' },
                  { id: 'info', icon: Info, label: 'Инфо' },
                ] as const).map(({ id, icon: Icon, label }) => (
                  <button key={id} onClick={() => setViewMode(id)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5 ${
                      viewMode === id ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'
                    }`}>
                    <Icon className="w-3.5 h-3.5" />{label}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <Button onClick={handleDownload}
                  className="bg-violet-600 hover:bg-violet-700 text-white shadow-lg shadow-violet-500/20 h-9 px-4 text-sm">
                  <Download className="w-3.5 h-3.5 mr-1.5" /> Скачать .pptx
                </Button>
                <Button onClick={() => setShowDeleteConfirm(true)} variant="ghost"
                  className="h-9 w-9 p-0 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10">
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Content area */}
            <div className="flex-1 min-h-0 overflow-hidden">
              <AnimatePresence mode="wait">
                {viewMode === 'slides' && (
                  <motion.div key="slides" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
                    <SlideViewer presentation={activePresentation} activeSlide={activeSlide} onSlideChange={setActiveSlide} />
                  </motion.div>
                )}
                {viewMode === 'outline' && (
                  <motion.div key="outline" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
                    <OutlineView presentation={activePresentation} onSlideClick={i => { setActiveSlide(i); setViewMode('slides'); }} />
                  </motion.div>
                )}
                {viewMode === 'info' && (
                  <motion.div key="info" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full overflow-y-auto custom-scrollbar space-y-4">
                    <div className="premium-glass rounded-2xl border border-white/5 p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <FileText className="w-4 h-4 text-violet-400" />
                        <h3 className="text-sm font-bold text-slate-200">Тема презентации</h3>
                      </div>
                      <p className="text-slate-300 text-sm leading-relaxed">{activePresentation.theme}</p>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { label: 'Слайдов', value: activePresentation.num_slides, icon: Layers },
                        { label: 'Превью', value: (activePresentation.slide_png_paths || []).length, icon: Monitor },
                        { label: 'Дата', value: new Date(activePresentation.timestamp).toLocaleDateString('ru-RU'), icon: Calendar },
                      ].map(({ label, value, icon: Icon }) => (
                        <div key={label} className="premium-glass rounded-xl border border-white/5 p-4">
                          <Icon className="w-4 h-4 text-slate-500 mb-2" />
                          <div className="text-xl font-bold text-white">{value}</div>
                          <div className="text-xs text-slate-500 mt-1">{label}</div>
                        </div>
                      ))}
                    </div>
                    {/* How to edit */}
                    <div className="premium-glass rounded-2xl border border-violet-500/15 p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Pencil className="w-4 h-4 text-violet-400" />
                        <h3 className="text-sm font-bold text-slate-200">Как редактировать</h3>
                      </div>
                      <ul className="space-y-2 text-xs text-slate-400">
                        <li className="flex items-start gap-2"><span className="text-violet-400 font-bold mt-0.5">→</span> <span>Нажмите на любой текст прямо в слайде — откроется редактор</span></li>
                        <li className="flex items-start gap-2"><span className="text-violet-400 font-bold mt-0.5">→</span> <span>На графических слайдах — выбирайте тип графика в нижней панели</span></li>
                        <li className="flex items-start gap-2"><span className="text-violet-400 font-bold mt-0.5">→</span> <span>В режиме «Структура» — навигация по всем слайдам</span></li>
                        <li className="flex items-start gap-2"><span className="text-violet-400 font-bold mt-0.5">→</span> <span>← → или Escape / F — клавиши навигации и полноэкранный режим</span></li>
                      </ul>
                    </div>
                    {activePresentation.reasoning && (
                      <div className="premium-glass rounded-2xl border border-white/5 p-5">
                        <div className="flex items-center gap-2 mb-3">
                          <Sparkles className="w-4 h-4 text-amber-400" />
                          <h3 className="text-sm font-bold text-slate-200">Методология AI</h3>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed">{activePresentation.reasoning}</p>
                      </div>
                    )}
                    <div className="premium-glass rounded-2xl border border-amber-500/10 p-4 flex items-start gap-3">
                      <RefreshCw className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-slate-400">
                        Для обновления данных — сгенерируйте новую презентацию через «Сгенерировать Презентацию».
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
            Выберите презентацию из истории
          </div>
        )}
      </div>

      {/* Delete confirm modal */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
              onClick={() => setShowDeleteConfirm(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-slate-900 border border-slate-700/50 rounded-2xl p-6 shadow-2xl max-w-md w-full">
              <h3 className="text-lg font-bold text-slate-200 mb-2">Удалить презентацию?</h3>
              <p className="text-sm text-slate-400 mb-6">Это действие нельзя отменить. Файл .pptx останется на диске.</p>
              <div className="flex justify-end gap-3">
                <button onClick={() => setShowDeleteConfirm(false)} className="px-4 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-800 transition-colors">Отмена</button>
                <button onClick={handleDelete} className="px-4 py-2 rounded-lg text-sm text-white bg-rose-500 hover:bg-rose-600 transition-colors">Да, удалить</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
