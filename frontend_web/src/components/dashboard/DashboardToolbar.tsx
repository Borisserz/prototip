import React, { useState } from 'react';
import { Download, Trash2, LayoutDashboard, Check, Loader2, FileText } from 'lucide-react';
import { Button } from "@/components/ui/button";

interface DashboardToolbarProps {
  onClear: () => void;
  onBackToChat: () => void;
  onExport: () => void;
  onExportWord: () => void;
  hasCharts: boolean;
  title?: string;
}

export const DashboardToolbar: React.FC<DashboardToolbarProps> = ({ onClear, onBackToChat, onExport, onExportWord, hasCharts, title }) => {
  const [exportState, setExportState] = useState<'idle' | 'loading' | 'done'>('idle');
  const [wordState, setWordState] = useState<'idle' | 'loading' | 'done'>('idle');

  const handleExport = async () => {
    setExportState('loading');
    try {
      await onExport();
      setExportState('done');
    } catch {
      setExportState('idle');
    } finally {
      setTimeout(() => setExportState('idle'), 3000);
    }
  };

  const handleExportWord = async () => {
    setWordState('loading');
    try {
      await onExportWord();
      setWordState('done');
    } catch {
      setWordState('idle');
    } finally {
      setTimeout(() => setWordState('idle'), 3000);
    }
  };

  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 premium-glass rounded-2xl border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.2)] relative overflow-hidden group">
      {/* Декоративный фон */}
      <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-accent/5 opacity-50 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" />
      
      <div className="flex items-center gap-3 relative z-10">
        <div className="w-10 h-10 rounded-xl bg-slate-800/80 border border-slate-700/50 flex items-center justify-center shadow-inner">
          <LayoutDashboard className="w-5 h-5 text-emerald-400" />
        </div>
        <div>
          <h2 className="text-lg font-bold text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-400">
            {title || "Главный Дашборд"}
          </h2>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-xs text-slate-400 font-medium tracking-wider uppercase">Live Analytics</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 w-full sm:w-auto relative z-10">
        <Button 
          variant="secondary"
          onClick={onBackToChat}
          className="flex-1 sm:flex-none bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all"
        >
          Вернуться к чату
        </Button>

        <Button 
          variant="outline"
          onClick={handleExport}
          disabled={exportState !== 'idle' || !hasCharts}
          className={`min-w-[110px] border-slate-700/50 transition-all duration-300 ${
            exportState === 'done' 
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
              : 'bg-slate-800/50 hover:bg-slate-700/50 text-slate-300'
          }`}
        >
          {exportState === 'loading' && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          {exportState === 'done'    && <Check className="w-4 h-4 mr-2 text-emerald-400" />}
          {exportState === 'idle'    && <Download className="w-4 h-4 mr-2" />}
          {exportState === 'loading' ? 'Создание PDF…' : exportState === 'done' ? 'Готово!' : 'PDF'}
        </Button>

        <Button 
          variant="outline"
          onClick={handleExportWord}
          disabled={wordState !== 'idle' || !hasCharts}
          className={`min-w-[110px] border-slate-700/50 transition-all duration-300 ${
            wordState === 'done' 
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
              : 'bg-slate-800/50 hover:bg-slate-700/50 text-slate-300'
          }`}
          title="Экспорт в Word (.docx)"
        >
          {wordState === 'loading' && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          {wordState === 'done'    && <Check className="w-4 h-4 mr-2 text-emerald-400" />}
          {wordState === 'idle'    && <FileText className="w-4 h-4 mr-2" />}
          {wordState === 'loading' ? 'Создание Word…' : wordState === 'done' ? 'Готово!' : 'Word'}
        </Button>

        <Button 
          variant="ghost"
          onClick={onClear}
          disabled={!hasCharts}
          className="text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 transition-colors px-3"
          title="Очистить дашборд"
        >
          <Trash2 className="w-5 h-5" />
        </Button>
      </div>
    </div>
  );
};
