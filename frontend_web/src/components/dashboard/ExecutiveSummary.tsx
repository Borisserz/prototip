import React, { useEffect, useState } from 'react';
import { TrendingUp, Users, Database, Zap, Settings2, X, CheckCircle2 } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, YAxis } from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';

const dummySparklineData1 = Array.from({ length: 15 }, () => ({ value: Math.random() * 100 + 50 }));
const dummySparklineData2 = Array.from({ length: 15 }, () => ({ value: Math.random() * 100 + 20 }));


// Animated Counter Component
const AnimatedCounter = ({ value }: { value: string }) => {
  const isPercent = value.includes('%');
  const numValue = parseFloat(value.replace(/,/g, '').replace('%', ''));
  
  const [current, setCurrent] = useState(0);
  
  useEffect(() => {
    let start = 0;
    const duration = 1500; // ms
    const increment = numValue / (duration / 16);
    
    const timer = setInterval(() => {
      start += increment;
      if (start >= numValue) {
        setCurrent(numValue);
        clearInterval(timer);
      } else {
        setCurrent(start);
      }
    }, 16);
    return () => clearInterval(timer);
  }, [numValue]);

  const displayValue = current.toLocaleString('en-US', {
    maximumFractionDigits: isPercent ? 1 : 0
  });

  return <span>{displayValue}{isPercent ? '%' : ''}</span>;
}

const KPICard = ({ title, value, delta, isPositive, icon: Icon, sparklineData, color, index, onClick }: any) => {
  const gradientId = `color-${title.replace(/\s+/g, '-')}`;

  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, delay: index * 0.1 }}
      onClick={onClick}
      className="glass-card p-4 rounded-2xl flex flex-col relative overflow-hidden group aspect-square justify-between shadow-lg cursor-pointer hover:shadow-2xl hover:scale-[1.02] hover:border-primary/50 transition-all duration-300"
    >
      <div className="absolute inset-0 bg-slate-900/0 group-hover:bg-slate-900/40 transition-colors z-20 pointer-events-none flex items-center justify-center">
         <div className="opacity-0 group-hover:opacity-100 bg-black/60 p-2.5 rounded-full backdrop-blur-md transform scale-90 group-hover:scale-100 transition-all shadow-[0_0_30px_rgba(0,0,0,0.8)] border border-white/10 text-white">
            <Settings2 className="w-5 h-5 text-teal-400" />
         </div>
      </div>
      <div className="flex justify-between items-start relative z-10">
        <div className={`p-2 rounded-xl bg-opacity-20`} style={{ backgroundColor: `${color}22`, color: color }}>
          <Icon className="w-5 h-5" />
        </div>
        <div className={`flex items-center text-[10px] font-bold px-2 py-0.5 rounded-full backdrop-blur-md ${isPositive ? 'text-emerald-400 bg-emerald-400/10 border border-emerald-400/20' : 'text-rose-400 bg-rose-400/10 border border-rose-400/20'}`}>
          {isPositive ? '+' : ''}{delta}%
        </div>
      </div>
      
      <div className="relative z-10 mt-auto pb-1">
        <span className="text-slate-400 text-[10px] 2xl:text-xs font-semibold uppercase tracking-wider block truncate">{title}</span>
        <div className="text-xl 2xl:text-2xl font-black text-white mt-1 tracking-tight drop-shadow-md truncate">
          <AnimatedCounter value={value} />
        </div>
      </div>
      
      <div className="absolute bottom-0 left-0 w-full h-1/2 opacity-30 group-hover:opacity-80 transition-opacity duration-500">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={sparklineData}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.6}/>
                <stop offset="95%" stopColor={color} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <YAxis domain={['dataMin - 10', 'dataMax + 10']} hide />
            <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} animationDuration={2000} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  );
};

const DEFAULT_METRICS = ['Начислено', 'Оплачено', 'Задолженность', 'Уровень сборов'];

export const ExecutiveSummary: React.FC = () => {
  const [kpiData, setKpiData] = useState<any[]>([]);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(() => {
    const saved = localStorage.getItem('dashboard_kpi_layout');
    return saved ? JSON.parse(saved) : DEFAULT_METRICS;
  });
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/kpi')
      .then(res => res.json())
      .then(data => {
        if (data.kpi) {
          setKpiData(data.kpi);
          // If the backend returns new metrics not in localstorage, we might need a fallback, but default handles it.
        }
      })
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    localStorage.setItem('dashboard_kpi_layout', JSON.stringify(selectedMetrics));
  }, [selectedMetrics]);

  const handleSelectMetric = (metricTitle: string) => {
    if (editingIndex === null) return;
    
    const existingIndex = selectedMetrics.indexOf(metricTitle);
    const newMetrics = [...selectedMetrics];
    
    if (existingIndex !== -1) {
      // Swap places if the chosen metric is already on the board
      newMetrics[existingIndex] = newMetrics[editingIndex];
    }
    
    newMetrics[editingIndex] = metricTitle;
    setSelectedMetrics(newMetrics);
    setEditingIndex(null);
  };

  const getIcon = (title: string) => {
    if (title.includes('Начислено')) return Database;
    if (title.includes('Оплачено')) return Zap;
    if (title.includes('Задолженность')) return Users;
    return TrendingUp;
  };
  
  const getColor = (status: string) => {
    if (status === 'good') return '#34d399';
    if (status === 'bad') return '#f87171';
    return '#38bdf8';
  };

  if (kpiData.length === 0) {
    return (
      <div className="grid grid-cols-2 gap-4 mb-6">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="animate-pulse aspect-square bg-slate-800/40 rounded-2xl border border-slate-700/30"></div>
        ))}
      </div>
    );
  }

  // Build the array of 4 objects to render based on selectedMetrics
  const renderData = selectedMetrics.map(title => {
    const found = kpiData.find(k => k.title === title);
    return found || kpiData[0]; // fallback if not found
  }).filter(Boolean);

  return (
    <>
      <div className="grid grid-cols-2 gap-4 mb-6">
        {renderData.slice(0, 4).map((kpi, idx) => (
          <KPICard 
            key={`${kpi.title}-${idx}`}
            title={kpi.title} 
            value={String(kpi.value)} 
            delta={parseFloat(kpi.trend) || 0} 
            isPositive={kpi.status === 'good'} 
            icon={getIcon(kpi.title)}
            color={getColor(kpi.status)}
            sparklineData={idx % 2 === 0 ? dummySparklineData1 : dummySparklineData2}
            index={idx}
            onClick={() => setEditingIndex(idx)}
          />
        ))}
      </div>

      <AnimatePresence>
        {editingIndex !== null && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md">
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="bg-slate-900 border border-slate-700/50 rounded-2xl w-full max-w-md overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.5)] flex flex-col glass-panel relative"
            >
              <div className="p-5 border-b border-slate-800/50 flex items-center justify-between bg-slate-950/40">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Settings2 className="w-5 h-5 text-teal-400" /> Настройка KPI
                </h2>
                <button onClick={() => setEditingIndex(null)} className="text-slate-400 hover:text-white transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-4 space-y-2 max-h-[60vh] overflow-y-auto">
                {kpiData.map((kpi) => {
                  const Icon = getIcon(kpi.title);
                  const isSelected = selectedMetrics.includes(kpi.title);
                  const isCurrentCell = selectedMetrics[editingIndex] === kpi.title;
                  
                  return (
                    <button
                      key={kpi.title}
                      onClick={() => handleSelectMetric(kpi.title)}
                      disabled={isCurrentCell}
                      className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all duration-200 text-left ${
                        isCurrentCell 
                          ? 'bg-teal-500/10 border-teal-500/30 cursor-default opacity-80'
                          : isSelected 
                            ? 'bg-slate-800/80 border-slate-700 hover:bg-slate-700 hover:border-slate-500'
                            : 'bg-slate-900/50 border-slate-800 hover:bg-slate-800 hover:border-slate-600'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${isCurrentCell ? 'bg-teal-500/20 text-teal-400' : 'bg-slate-800 text-slate-400'}`}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <div>
                          <p className={`text-sm font-semibold ${isCurrentCell ? 'text-teal-400' : 'text-white'}`}>{kpi.title}</p>
                          <p className="text-xs text-slate-400 font-mono mt-0.5">{kpi.value}</p>
                        </div>
                      </div>
                      <div className="flex flex-col items-end">
                        {isCurrentCell ? (
                          <span className="text-[10px] uppercase text-teal-400 font-semibold bg-teal-500/10 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> Текущая
                          </span>
                        ) : isSelected ? (
                          <span className="text-[10px] uppercase text-slate-500 font-semibold bg-slate-800 px-2 py-0.5 rounded-full">
                            В сетке (Swap)
                          </span>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};
