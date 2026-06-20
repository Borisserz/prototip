import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, TrendingUp, TrendingDown, AlertTriangle, Lightbulb } from 'lucide-react';

interface Insight {
  type: 'positive' | 'negative' | 'warning';
  text: string;
}

export const AutoInsights: React.FC = () => {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/insights')
      .then(res => res.json())
      .then(data => {
        if (data.insights) setInsights(data.insights);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const getIcon = (type: string) => {
    switch (type) {
      case 'positive': return <TrendingUp className="w-5 h-5 text-emerald-400" />;
      case 'negative': return <TrendingDown className="w-5 h-5 text-rose-400" />;
      case 'warning': return <AlertTriangle className="w-5 h-5 text-amber-400" />;
      default: return <Lightbulb className="w-5 h-5 text-blue-400" />;
    }
  };

  const getBgColor = (type: string) => {
    switch (type) {
      case 'positive': return 'bg-emerald-500/10 border-emerald-500/20 hover:border-emerald-500/40 hover:shadow-[0_0_15px_rgba(16,185,129,0.15)]';
      case 'negative': return 'bg-rose-500/10 border-rose-500/20 hover:border-rose-500/40 hover:shadow-[0_0_15px_rgba(244,63,94,0.15)]';
      case 'warning': return 'bg-amber-500/10 border-amber-500/20 hover:border-amber-500/40 hover:shadow-[0_0_15px_rgba(245,158,11,0.15)]';
      default: return 'bg-slate-800/50 border-slate-700/50 hover:border-slate-600/50 hover:shadow-[0_0_15px_rgba(148,163,184,0.1)]';
    }
  };

  return (
    <div className="rounded-2xl border border-white/10 shadow-[0_0_40px_rgba(14,165,233,0.1)] overflow-hidden mb-6 flex flex-col bg-gradient-to-b from-slate-900/90 to-slate-950/90 backdrop-blur-2xl relative">
      <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 via-purple-500/5 to-teal-500/5 pointer-events-none"></div>
      
      <div className="p-4 border-b border-white/5 flex items-center justify-between bg-white/5 relative z-10">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/20 border border-indigo-500/30 shadow-[0_0_10px_rgba(99,102,241,0.3)]">
            <Brain className="w-4 h-4 text-indigo-400" />
          </div>
          <h3 className="text-xs font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400 tracking-widest uppercase">Auto-Insights</h3>
        </div>
        <div className="flex gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/50"></div>
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/20"></div>
        </div>
      </div>
      
      <div className="p-4 flex flex-col gap-3 relative z-10">
        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div 
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-3"
            >
              {[1, 2, 3].map(i => (
                <div key={i} className="flex gap-3 items-start relative overflow-hidden rounded-xl bg-slate-800/20 p-3 border border-white/5 before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_2s_infinite] before:bg-gradient-to-r before:from-transparent before:via-white/5 before:to-transparent">
                  <div className="w-8 h-8 rounded-lg bg-slate-700/50 flex-shrink-0 animate-pulse"></div>
                  <div className="flex-1 space-y-2 py-1">
                    <div className="h-2 bg-slate-700/50 rounded w-3/4 animate-pulse"></div>
                    <div className="h-2 bg-slate-700/50 rounded w-1/2 animate-pulse"></div>
                  </div>
                </div>
              ))}
            </motion.div>
          ) : (
            <motion.div 
              key="content"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-3"
            >
              {insights.map((insight, idx) => (
                <motion.div 
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.1 }}
                  key={idx} 
                  className={`flex gap-3 items-start p-3 rounded-xl border hover:-translate-y-0.5 transition-all duration-300 group cursor-default ${getBgColor(insight.type)}`}
                >
                  <div className="mt-0.5 transform group-hover:scale-110 transition-transform duration-300 drop-shadow-[0_0_8px_rgba(255,255,255,0.3)]">{getIcon(insight.type)}</div>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed font-medium group-hover:text-white transition-colors">{insight.text}</p>
                </motion.div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};
