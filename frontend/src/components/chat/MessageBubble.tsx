import React from 'react';
import { motion } from "framer-motion";
import { Search, Sparkles, Download, Presentation, Database, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/App"; // Ensure cn is exported
import { DynamicChart } from "./DynamicChart";
import { Message, useChatStore } from "../../store/useChatStore";
import { FilterWidget } from './widgets/FilterWidget';
import { API_BASE } from "@/lib/config";

interface MessageBubbleProps {
  msg: Message;
  isLastLoading: boolean;
  onPin: (content: string) => void;
  onChartClick: (prompt: string, drilldown?: { key: string; value: string; action: string }) => void;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ msg, isLastLoading, onPin, onChartClick }) => {
  const isAnalystMode = useChatStore((state) => state.isAnalystMode);
  const [showSql, setShowSql] = React.useState(false);
  const [showDebates, setShowDebates] = React.useState(true);
  
  const hasFilterWidget = msg.content && msg.content.includes('[WIDGET:FILTER]');
  const cleanContent = msg.content ? msg.content.replace('[WIDGET:FILTER]', '').trim() : '';
  // Курсор: показывается в последнем сообщении ассистента пока идёт typewriter-анимация
  const isTyping = msg.isStreaming === true;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className={cn("flex w-full", msg.role === 'user' ? "justify-end" : "justify-start")}
    >
      <div className={cn(
        "flex gap-4 max-w-[90%]", 
        msg.role === 'user' ? "flex-row-reverse" : "flex-row"
      )}>
        {/* Avatar */}
        <div className={cn(
          "w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 shadow-lg",
          msg.role === 'user' 
            ? "bg-primary shadow-primary/20" 
            : "bg-gradient-to-br from-primary to-teal-500 animate-pulse-glow"
        )}>
          {msg.role === 'user' ? <Search className="w-5 h-5 text-white" /> : <Sparkles className="w-5 h-5 text-white" />}
        </div>
        
        {/* Content */}
        <div className={cn(
          "flex flex-col gap-2",
          msg.role === 'user' ? "items-end" : "items-start"
        )}>
          <div className={cn(
            "p-6 rounded-3xl shadow-xl",
            msg.role === 'user' 
              ? "bg-primary text-white rounded-tr-sm shadow-primary/20" 
              : "bg-slate-800/80 backdrop-blur-md border border-slate-700 text-slate-100 rounded-tl-sm"
          )}>
            {msg.role === 'user' ? (
              <p className="text-base leading-relaxed">{msg.content}</p>
            ) : (
              <div className="flex flex-col gap-2">
                {hasFilterWidget && <FilterWidget onApply={(f) => console.log('Applied', f)} />}
                <div className="prose prose-invert max-w-none">
                  {cleanContent.split('```').map((part, idx) => {
                if (idx % 2 === 1) {
                  const codeContent = part.replace(/^(json|javascript|jsx|tsx)\n/, '');
                  if (codeContent.includes('"chart_type"') || (codeContent.includes('chart_type') && codeContent.includes('data'))) {
                    return <DynamicChart key={idx} content={codeContent} onPin={onPin} onChartClick={onChartClick} />;
                  }
                  return (
                    <pre key={idx} className="bg-slate-900/80 p-4 rounded-xl border border-slate-700 text-sm overflow-x-auto text-primary">
                      <code>{codeContent}</code>
                    </pre>
                  );
                }
                if (!part.trim()) return null;
                return (
                  <div key={idx} className="text-base leading-relaxed space-y-4">
                    {part.split('\n').map((line, lidx) => {
                      if (!line.trim()) return <div key={lidx} className="h-2"></div>;
                      
                      const renderInlineMarkdown = (text: string) => {
                        const chunks = text.split(/(\*\*.*?\*\*)/g);
                        return chunks.map((chunk, i) => {
                          if (chunk.startsWith('**') && chunk.endsWith('**')) {
                            return <strong key={i} className="text-white font-bold">{chunk.slice(2, -2)}</strong>;
                          }
                          return chunk;
                        });
                      };

                      if (line.startsWith('### ')) return <h3 key={lidx} className="text-lg font-bold text-white mt-4">{renderInlineMarkdown(line.replace('### ', ''))}</h3>;
                      if (line.startsWith('- ')) return <li key={lidx} className="ml-4 text-slate-200">{renderInlineMarkdown(line.replace('- ', ''))}</li>;
                      return <p key={lidx}>{renderInlineMarkdown(line)}</p>;
                    })}
                  </div>
                );
              })}
              </div>
              
              {/* Мигающий курсор во время typewriter-анимации */}
              {isTyping && (
                <span
                  style={{
                    display: 'inline-block',
                    width: '2px',
                    height: '1.1em',
                    background: 'currentColor',
                    marginLeft: '2px',
                    verticalAlign: 'text-bottom',
                    animation: 'blink-cursor 0.7s step-end infinite',
                  }}
                  aria-hidden="true"
                />
              )}
              
              {msg.pptx_path && (
                <motion.div 
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                  className="mt-4 rounded-xl border border-slate-700/50 bg-gradient-to-br from-slate-800/80 to-slate-900/80 overflow-hidden shadow-lg group"
                >
                  <div className="p-4 flex items-start gap-4">
                    <div className="w-12 h-12 rounded-lg bg-rose-500/10 flex items-center justify-center flex-shrink-0 border border-rose-500/20">
                      <Presentation className="w-6 h-6 text-rose-400" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-white mb-1">Аналитическая презентация готова</p>
                      <p className="text-xs text-slate-400 mb-3 truncate max-w-[250px]">{msg.pptx_path.split('/').pop()}</p>
                      
                      <div className="flex gap-2">
                        <Button 
                          size="sm"
                          onClick={() => {
                            const link = document.createElement('a');
                            link.href = `${API_BASE}/api/v1/download?file=${encodeURIComponent(msg.pptx_path!)}`;
                            link.download = msg.pptx_path!.split('/').pop() || 'presentation.pptx';
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                          }}
                          className="bg-slate-800 border border-slate-700 hover:bg-slate-700 text-white shadow-sm h-8 text-xs w-full transition-colors"
                        >
                          <Download className="w-3 h-3 mr-2 text-rose-400" /> Скачать (.pptx)
                        </Button>
                      </div>
                    </div>
                  </div>
                  <div className="h-1 w-full bg-gradient-to-r from-rose-500 via-primary to-emerald-500 opacity-50 group-hover:opacity-100 transition-opacity"></div>
                </motion.div>
              )}

              {msg.excel_path && (
                <motion.div 
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                  className="mt-4 rounded-xl border border-slate-700/50 bg-gradient-to-br from-slate-800/80 to-slate-900/80 overflow-hidden shadow-lg group"
                >
                  <div className="p-4 flex items-start gap-4">
                    <div className="w-12 h-12 rounded-lg bg-emerald-500/10 flex items-center justify-center flex-shrink-0 border border-emerald-500/20">
                      <Database className="w-6 h-6 text-emerald-400" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-white mb-1">Excel-отчет сформирован</p>
                      <p className="text-xs text-slate-400 mb-3 truncate max-w-[250px]">{msg.excel_path.split('/').pop()}</p>
                      
                      <div className="flex gap-2">
                        <Button 
                          size="sm"
                          onClick={() => {
                            const link = document.createElement('a');
                            link.href = `${API_BASE}/api/v1/download?file=${encodeURIComponent(msg.excel_path!)}`;
                            link.download = msg.excel_path!.split('/').pop() || 'report.xlsx';
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                          }}
                          className="bg-slate-800 border border-slate-700 hover:bg-slate-700 text-white shadow-sm h-8 text-xs w-full transition-colors"
                        >
                          <Download className="w-3 h-3 mr-2 text-emerald-400" /> Скачать (.xlsx)
                        </Button>
                      </div>
                    </div>
                  </div>
                  <div className="h-1 w-full bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-500 opacity-50 group-hover:opacity-100 transition-opacity"></div>
                </motion.div>
              )}
              
              {isAnalystMode && msg.sql && (
                <div className="mt-4 border border-slate-700/50 bg-slate-900/50 rounded-xl overflow-hidden">
                  <button 
                    onClick={() => setShowSql(!showSql)}
                    className="w-full px-4 py-2 flex items-center justify-between hover:bg-slate-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-2 text-slate-300">
                      <Database className="w-4 h-4 text-primary" />
                      <span className="text-sm font-medium">SQL Запрос (ClickHouse)</span>
                    </div>
                    {showSql ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                  </button>
                  {showSql && (
                    <motion.div 
                      initial={{ height: 0, opacity: 0 }} 
                      animate={{ height: "auto", opacity: 1 }}
                      className="p-4 border-t border-slate-700/50 bg-slate-950"
                    >
                      <pre className="text-xs text-primary font-mono whitespace-pre-wrap overflow-x-auto">
                        <code>{msg.sql}</code>
                      </pre>
                    </motion.div>
                  )}
                </div>
              )}
              
              {msg.debates && msg.debates.length > 0 && (
                <div className="mt-4 border border-teal-500/30 bg-slate-900/40 backdrop-blur-md rounded-2xl overflow-hidden shadow-lg group">
                  <button 
                    onClick={() => setShowDebates(!showDebates)}
                    className="w-full px-4 py-3 flex items-center justify-between bg-gradient-to-r from-teal-500/10 to-transparent hover:from-teal-500/20 transition-all duration-300"
                  >
                    <div className="flex items-center gap-3 text-slate-200">
                      <div className="p-1.5 rounded-lg bg-teal-500/20 border border-teal-500/30 group-hover:scale-110 transition-transform">
                        <Sparkles className="w-4 h-4 text-teal-400" />
                      </div>
                      <span className="text-sm font-semibold tracking-wide">Внутренний процесс агентов <span className="text-teal-400">({msg.debates.length})</span></span>
                    </div>
                    {showDebates ? <ChevronUp className="w-5 h-5 text-teal-400/70" /> : <ChevronDown className="w-5 h-5 text-teal-400/70" />}
                  </button>
                  {showDebates && (
                    <motion.div 
                      initial={{ height: 0, opacity: 0 }} 
                      animate={{ height: "auto", opacity: 1 }}
                      className="p-4 border-t border-teal-500/20 bg-slate-950/50 flex flex-col gap-3"
                    >
                      {msg.debates.map((d, idx) => (
                        <motion.div 
                          key={idx} 
                          initial={{ x: -10, opacity: 0 }}
                          animate={{ x: 0, opacity: 1 }}
                          transition={{ delay: idx * 0.1 }}
                          className="text-sm text-slate-300 border-l-2 border-teal-500 pl-4 py-2 bg-slate-900/30 rounded-r-lg"
                        >
                          <strong className={cn(
                            "mr-2 font-bold",
                            d.role === "Analyst" ? "text-indigo-400" : "text-rose-400"
                          )}>{d.role}:</strong> 
                          <span className="opacity-90">{d.content}</span>
                        </motion.div>
                      ))}
                    </motion.div>
                  )}
                </div>
              )}
              
              {isLastLoading && (
                <div className="flex items-center gap-2 text-primary mt-2">
                  <span className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }}></span>
                  <span className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }}></span>
                  <span className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }}></span>
                </div>
              )}
            </div>
          )}
        </div>
        </div>
      </div>
    </motion.div>
  );
};