import React, { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bar, BarChart, Pie, PieChart, Line, LineChart, Area, AreaChart, ScatterChart, Scatter, Treemap, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, CartesianGrid, Cell } from "recharts";
import { Activity, Download, Pin, TableProperties, Presentation, Mail, Info, GitCompare, Database, Maximize, X } from "lucide-react";

import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { cn } from "@/App";
import { exportToExcel } from '../../utils/xlsxWriter';
import { exportChartToPNG } from '../../utils/chartPngExport';
import { formatCompactNumber } from '../../utils/formatters';

const COLORS = [
  '#38bdf8', '#818cf8', '#c084fc', '#34d399', '#f472b6', 
  '#fbbf24', '#f87171', '#2dd4bf', '#a78bfa', '#fb923c'
];

const COLUMN_TRANSLATIONS: Record<string, string> = {
  'REGION': 'Регион',
  'TOTAL_ACCRUED': 'Начислено',
  'TOTAL_PaiD': 'Оплачено',
  'TOTAL_DEBT': 'Задолженность',
  'TAX_TYPE': 'Вид налога',
  'PERIOD': 'Период',
  'PENALTY': 'Пеня',
  'STATUS': 'Статус',
  'category': 'Категория',
  'value': 'Значение'
};
const translateCol = (col: string) => COLUMN_TRANSLATIONS[col] || COLUMN_TRANSLATIONS[col.toUpperCase()] || col;

const renderCustomizedLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
  if (percent < 0.04) return null; // Don't show labels for tiny slices (< 4%)
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * Math.PI / 180);
  const y = cy + radius * Math.sin(-midAngle * Math.PI / 180);

  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight="bold" style={{ pointerEvents: 'none', textShadow: '0px 1px 3px rgba(0,0,0,0.8)' }}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
};

interface DynamicChartProps {
  content: string;
  onPin?: (c: string) => void;
  isPinnedView?: boolean;
  onChartClick?: (prompt: string, drilldown?: { key: string; value: string; action: string }) => void;
}

export const DynamicChart: React.FC<DynamicChartProps> = ({ content, onPin, isPinnedView = false, onChartClick }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const expandedChartRef = useRef<HTMLDivElement>(null);
  const [contextMenu, setContextMenu] = useState<{x: number, y: number, key: string, value: any} | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isTableCollapsed, setIsTableCollapsed] = useState(true);
  const [overrideType, setOverrideType] = useState<string | null>(null);
  const chartId = React.useId().replace(/:/g, '');

  const handleChartElementClick = (key: string, value: any, _e?: any) => {
    // recharts иногда не передаёт clientX — открываем меню по центру экрана
    if (!key || value === undefined || value === null) return;
    setContextMenu({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
      key,
      value
    });
  };

  const closeContextMenu = () => setContextMenu(null);

  const handleExportExcel = (exportData: any[], chartTitle: string) => {
    exportToExcel(exportData, chartTitle || 'report');
  };

  try {
    const trimmedContent = typeof content === 'string' ? content.trim() : content;
    let parsed = JSON.parse(trimmedContent);
    if (typeof parsed === 'string') {
      try { parsed = JSON.parse(parsed.trim()); } catch { return <div className="whitespace-pre-wrap leading-relaxed">{content}</div>; }
    }

    if (Array.isArray(parsed) && parsed.length > 0 && typeof parsed[0] === 'object' && parsed[0].chart_type) {
      return (
        <div className="flex flex-col gap-4">
          {parsed.map((chartObj, idx) => (
            <DynamicChart key={idx} content={JSON.stringify(chartObj)} onPin={onPin} isPinnedView={isPinnedView} onChartClick={onChartClick} />
          ))}
        </div>
      );
    }

    if (parsed && typeof parsed === 'object' && parsed.chart_type && parsed.data) {
      const { chart_type, data, title } = parsed;
      const activeChartType = overrideType || chart_type;
      
      const renderChart = (expanded = false) => {
        if (!data || data.length === 0) return <div className="text-slate-400 font-mono text-sm border border-dashed border-slate-700 p-4 rounded-xl">No data returned.</div>;
        
        const isNumeric = (k: string) => data.some((row: any) => typeof row[k] === 'number');
        const numericKeys = Object.keys(data[0]).filter(k => isNumeric(k) && k !== '_task');
        
        const xKeyCandidate = Object.keys(data[0]).find(k => ['name', 'category', 'label', 'period', 'region'].includes(k.toLowerCase()));
        const xKey = xKeyCandidate || Object.keys(data[0]).find(k => !isNumeric(k) && k !== '_task') || Object.keys(data[0])[0];
        
        const keys = numericKeys.length > 0 ? numericKeys : Object.keys(data[0]).filter(k => k !== xKey && k !== '_task');
        const yKey = keys[0];

        // схлопываем дубли по xKey — иначе на детальных данных получается каша
        const aggMap = new Map();
        data.forEach((row: any) => {
          const xVal = row[xKey] || row.name || 'Unknown';
          if (!aggMap.has(xVal)) {
            aggMap.set(xVal, { ...row, [xKey]: xVal });
          } else {
            const existing = aggMap.get(xVal);
            keys.forEach(k => {
              if (typeof row[k] === 'number') {
                existing[k] = (existing[k] || 0) + row[k];
              }
            });
          }
        });
        const aggregatedData = Array.from(aggMap.values());
        if (xKey.toLowerCase() === 'period') {
          aggregatedData.sort((a, b) => String(a[xKey]).localeCompare(String(b[xKey])));
        } else if (keys.length > 0) {
          aggregatedData.sort((a, b) => (Number(b[keys[0]]) || 0) - (Number(a[keys[0]]) || 0));
        }

        const CustomTooltip = ({ active, payload, label }: any) => {
          if (active && payload && payload.length) {
            return (
              <div className="bg-slate-900 border border-slate-700 p-2 rounded shadow-lg text-xs font-sans z-50">
                <p className="font-bold mb-2 text-slate-200 uppercase tracking-wider border-b border-slate-700 pb-1">{label}</p>
                {payload.map((entry: any, index: number) => (
                  <p key={`item-${index}`} className="flex justify-between gap-4 items-center my-1">
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: entry.color }}></span>
                      <span className="text-slate-300">{translateCol(entry.name)}</span>
                    </span>
                    <span className="font-bold text-white tracking-wide">{typeof entry.value === 'number' ? entry.value.toLocaleString('ru-RU') : entry.value}</span>
                  </p>
                ))}
              </div>
            );
          }
          return null;
        };

        const renderLegendText = (value: string) => {
          return <span className="text-slate-300">{translateCol(value)}</span>;
        };

        const renderDefs = () => (
          <defs>
            {COLORS.map((color, idx) => (
              <linearGradient key={`grad-${idx}`} id={`colorGrad-${chartId}-${idx}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.8}/>
                <stop offset="95%" stopColor={color} stopOpacity={0.2}/>
              </linearGradient>
            ))}
          </defs>
        );

        const isBar = ['bar', 'grouped_bar', 'stacked_bar', 'horizontal_bar', 'waterfall', 'heatmap'].includes(activeChartType);
        const isPie = activeChartType === 'pie' || activeChartType === 'donut';
        const isLine = activeChartType === 'line' || activeChartType === 'area';
        const isScatter = activeChartType === 'scatter';
        const isTreemap = activeChartType === 'treemap';
        const isKpi = activeChartType === 'kpi';
        
        const hasValidChart = isBar || isPie || isLine || isScatter || isTreemap || isKpi;

        const renderChartVisual = (expanded = false) => {
          if (!hasValidChart) return null;
          const h = expanded || isPinnedView ? "100%" : 300;
          const showInteractions = !isPinnedView || expanded;

          if (isKpi) {
            return (
              <div className="flex flex-col items-center justify-center h-full w-full py-10" style={{ height: h }}>
                <div className="text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-teal-400 to-indigo-400">
                  {aggregatedData.length > 0 && keys.length > 0 ? (typeof aggregatedData[0][keys[0]] === 'number' ? aggregatedData[0][keys[0]].toLocaleString('ru-RU') : aggregatedData[0][keys[0]]) : 'N/A'}
                </div>
                <div className="text-slate-400 mt-2 text-sm uppercase tracking-wider">{keys.length > 0 ? translateCol(keys[0]) : ''}</div>
              </div>
            );
          }

          if (isBar) {
            const isHorizontal = activeChartType === 'horizontal_bar';
            const isStacked = activeChartType === 'stacked_bar';
            return (
              <ResponsiveContainer width="100%" height={h}>
                <BarChart layout={isHorizontal ? "vertical" : "horizontal"} data={aggregatedData} margin={{ top: 20, right: 20, left: isHorizontal ? 40 : 10, bottom: isPinnedView ? 0 : 20 }}>
                  {renderDefs()}
                  <CartesianGrid strokeDasharray="3 3" horizontal={!isHorizontal} vertical={isHorizontal} stroke="rgba(255,255,255,0.05)" />
                  <XAxis type={isHorizontal ? "number" : "category"} dataKey={isHorizontal ? undefined : xKey} tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} tickFormatter={isHorizontal ? formatCompactNumber : undefined} />
                  <YAxis type={isHorizontal ? "category" : "number"} dataKey={isHorizontal ? xKey : undefined} tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} width={isHorizontal ? 80 : 35} tickFormatter={!isHorizontal ? formatCompactNumber : undefined} />
                  {showInteractions && <Tooltip content={<CustomTooltip />} cursor={{fill: 'rgba(255,255,255,0.02)'}} />}
                  <Legend wrapperStyle={{paddingTop: isPinnedView ? '5px' : '20px', fontSize: '11px', paddingBottom: isPinnedView ? '10px' : '0'}} iconType="square" formatter={renderLegendText} />
                  {keys.map((k, i) => (
                    <Bar key={k} dataKey={k} stackId={isStacked ? "a" : undefined} fill={`url(#colorGrad-${chartId}-${i % COLORS.length})`} radius={isHorizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} animationDuration={1500} onClick={showInteractions ? (data: any, _: number, e: any) => handleChartElementClick(xKey, data[xKey] || data.name, e) : undefined} style={{ cursor: showInteractions ? 'pointer' : 'default' }} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            );
          } else if (isPie) {
            const isDonut = activeChartType === 'donut';
            return (
              <ResponsiveContainer width="100%" height={h}>
                <PieChart margin={{ bottom: isPinnedView ? 0 : 20 }}>
                  {showInteractions && <Tooltip content={<CustomTooltip />} />}
                  <Legend verticalAlign="bottom" wrapperStyle={{ paddingTop: isPinnedView ? '5px' : '20px', fontSize: '11px', paddingBottom: isPinnedView ? '10px' : '0' }} iconType="square" formatter={renderLegendText} />
                  <Pie data={aggregatedData} dataKey={yKey} nameKey={xKey} cx="50%" cy={isPinnedView ? "40%" : "45%"} labelLine={false} label={renderCustomizedLabel} innerRadius={expanded ? (isDonut ? 100 : 0) : (isDonut ? 50 : 0)} outerRadius={expanded ? 160 : (isPinnedView ? 80 : 100)} paddingAngle={isDonut ? 3 : 0} stroke="none" animationDuration={1500} onClick={showInteractions ? (data: any, _: number, e: any) => handleChartElementClick(xKey, data[xKey] || data.name, e) : undefined} style={{ cursor: showInteractions ? 'pointer' : 'default' }}>
                    {aggregatedData.map((_: any, index: number) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            );
          } else if (isLine) {
            const isArea = activeChartType === 'area';
            if (isArea) {
              return (
                <ResponsiveContainer width="100%" height={h}>
                  <AreaChart data={aggregatedData} margin={{ top: 20, right: 20, left: 10, bottom: isPinnedView ? 0 : 20 }}>
                    {renderDefs()}
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey={xKey} tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} />
                    <YAxis tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} width={35} tickFormatter={formatCompactNumber} />
                    {showInteractions && <Tooltip content={<CustomTooltip />} />}
                    <Legend wrapperStyle={{paddingTop: isPinnedView ? '5px' : '20px', fontSize: '11px', paddingBottom: isPinnedView ? '10px' : '0'}} iconType="square" formatter={renderLegendText} />
                    {keys.map((k, i) => (
                      <Area type="monotone" key={k} dataKey={k} stroke={COLORS[i % COLORS.length]} fill={`url(#colorGrad-${chartId}-${i % COLORS.length})`} strokeWidth={3} dot={{r: 4, strokeWidth: 2, fill: '#0f172a'}} animationDuration={1500} activeDot={showInteractions ? { r: 6, stroke: '#fff', onClick: (e: any, payload: any) => handleChartElementClick(xKey, payload.payload[xKey] || payload.payload.name, e) } : false} style={{ cursor: showInteractions ? 'pointer' : 'default' }} />
                    ))}
                  </AreaChart>
                </ResponsiveContainer>
              );
            }
            return (
              <ResponsiveContainer width="100%" height={h}>
                <LineChart data={aggregatedData} margin={{ top: 20, right: 20, left: 10, bottom: isPinnedView ? 0 : 20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey={xKey} tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} />
                  <YAxis tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} width={35} tickFormatter={formatCompactNumber} />
                  {showInteractions && <Tooltip content={<CustomTooltip />} />}
                  <Legend wrapperStyle={{paddingTop: isPinnedView ? '5px' : '20px', fontSize: '11px', paddingBottom: isPinnedView ? '10px' : '0'}} iconType="square" formatter={renderLegendText} />
                  {keys.map((k, i) => (
                    <Line type="monotone" key={k} dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={3} dot={{r: 4, strokeWidth: 2, fill: '#0f172a'}} animationDuration={1500} activeDot={showInteractions ? { r: 6, stroke: '#fff', onClick: (e: any, payload: any) => handleChartElementClick(xKey, payload.payload[xKey] || payload.payload.name, e) } : false} style={{ cursor: showInteractions ? 'pointer' : 'default' }} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            );
          } else if (isScatter) {
            return (
              <ResponsiveContainer width="100%" height={h}>
                <ScatterChart margin={{ top: 20, right: 20, left: 10, bottom: isPinnedView ? 0 : 20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey={xKey} type="category" tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} />
                  <YAxis dataKey={yKey} type="number" tick={{fill: '#94a3b8', fontSize: 11}} axisLine={false} tickLine={false} width={35} tickFormatter={formatCompactNumber} />
                  {showInteractions && <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3' }} />}
                  <Legend wrapperStyle={{paddingTop: isPinnedView ? '5px' : '20px', fontSize: '11px', paddingBottom: isPinnedView ? '10px' : '0'}} iconType="square" formatter={renderLegendText} />
                  {keys.map((k, i) => (
                    <Scatter key={k} name={k} data={aggregatedData} fill={COLORS[i % COLORS.length]} style={{ cursor: showInteractions ? 'pointer' : 'default' }} onClick={showInteractions ? (data: any, _: number, e: any) => handleChartElementClick(xKey, data[xKey] || data.name, e) : undefined} />
                  ))}
                </ScatterChart>
              </ResponsiveContainer>
            );
          } else if (isTreemap) {
            // для treemap нужны поля name и size
            const treemapData = aggregatedData.map((d: any) => ({
              name: d[xKey] || d.name || 'Unknown',
              size: Number(d[yKey]) || 0,
              ...d
            }));
            
            return (
              <ResponsiveContainer width="100%" height={h}>
                <Treemap
                  data={treemapData}
                  dataKey="size"
                  aspectRatio={4 / 3}
                  stroke="#fff"
                  fill="#8884d8"
                  onClick={showInteractions ? ((node: any) => handleChartElementClick(xKey, node?.name || node?.[xKey], node)) : undefined}
                >
                  {showInteractions && <Tooltip content={<CustomTooltip />} />}
                </Treemap>
              </ResponsiveContainer>
            );
          }
          return null;
        };

        const renderTable = () => (
          <div className="overflow-x-auto custom-scrollbar w-full">
            <table className="w-full text-sm text-left text-slate-300 border-collapse">
              <thead className="bg-slate-800/50 text-slate-100 border-b border-slate-700">
                <tr>
                  {Object.keys(data[0]).map((k) => (
                    <th key={k} className="px-4 py-3 font-medium uppercase tracking-wider text-xs">{translateCol(k)}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {data.map((row: any, i: number) => (
                  <tr key={i} className="hover:bg-white/5 transition-colors cursor-pointer" onClick={(e) => handleChartElementClick(xKey, row[xKey], e)}>
                    {Object.values(row).map((val: any, j: number) => (
                      <td key={j} className="px-4 py-3 whitespace-nowrap">{typeof val === 'number' ? val.toLocaleString('ru-RU') : String(val)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );

        return (
          <div className="flex flex-col h-full w-full">
            <div className="flex-1 min-h-0 w-full">
              {hasValidChart && renderChartVisual(expanded)}
            </div>
            <div className="mt-4 pt-4 border-t border-slate-700/50">
              <button 
                onClick={() => setIsTableCollapsed(!isTableCollapsed)}
                className={cn("flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors w-full", isPinnedView ? "py-1" : "py-2")}
              >
                <Database className="w-4 h-4 text-emerald-400" />
                <span className="font-medium">{isTableCollapsed ? 'Показать исходную таблицу' : 'Скрыть таблицу'}</span>
              </button>
              <AnimatePresence>
                {(!isTableCollapsed || !hasValidChart) && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="mt-4 w-full"
                  >
                    {renderTable()}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        );
      };

      const renderHeader = (isModal = false) => (
        <div className={cn("border-b border-white/5 bg-slate-900/40 flex items-center justify-between z-10 relative", isPinnedView && !isModal ? "px-4 py-3" : "px-5 py-4")}>
          <div className="flex items-center gap-3 overflow-hidden">
            {!isPinnedView && (
              <div className={cn("rounded-lg shadow-[0_0_15px_rgba(56,189,248,0.2)] flex-shrink-0 p-2 bg-primary/20")}>
                <Activity className="text-primary w-4 h-4" />
              </div>
            )}
            <span className={cn("font-semibold text-slate-100", isPinnedView && !isModal ? "text-sm truncate leading-tight tracking-wide" : "text-base")}>{title}</span>
          </div>
          <div className={cn("flex flex-wrap items-center gap-1", isModal ? "opacity-100" : "opacity-90 hover:opacity-100 transition-opacity")}>
            <select 
              value={activeChartType}
              onChange={(e) => setOverrideType(e.target.value)}
              className="bg-slate-800 text-slate-300 text-xs rounded border border-slate-700 px-2 h-8 mr-2 outline-none focus:border-primary/50 cursor-pointer"
            >
              <option value="bar">Bar</option>
              <option value="grouped_bar">Grouped Bar</option>
              <option value="stacked_bar">Stacked Bar</option>
              <option value="horizontal_bar">Horizontal Bar</option>
              <option value="line">Line</option>
              <option value="area">Area</option>
              <option value="pie">Pie</option>
              <option value="donut">Donut</option>
              <option value="scatter">Scatter</option>
              <option value="waterfall">Waterfall</option>
              <option value="kpi">KPI</option>
              <option value="heatmap">Heatmap</option>
              <option value="treemap">Treemap</option>
            </select>
            {onPin && !isPinnedView && !isModal && (
              <Button variant="ghost" size="sm" onClick={() => onPin(content)} className="flex items-center gap-1.5 h-8 px-2.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors shadow-sm">
                <Pin className="w-3 h-3" /> Pin
              </Button>
            )}
            {(!isPinnedView || isModal) && (
              <>
                <Button variant="ghost" size="sm" onClick={() => exportChartToPNG(parsed, title || 'chart')} className="flex items-center gap-1.5 h-8 px-2.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors shadow-sm">
                  <Download className="w-3 h-3" /> PNG
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handleExportExcel(data, title || 'report')} className="flex items-center gap-1.5 h-8 px-2.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors shadow-sm hidden sm:flex">
                  <Download className="w-3 h-3" /> Excel
                </Button>
                <Button variant="ghost" size="sm" onClick={() => { if(onChartClick) onChartClick("Сделай подробную презентацию по этим данным") }} className="flex items-center gap-1.5 h-8 px-2.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors shadow-sm hidden lg:flex">
                  <Presentation className="w-3 h-3" /> В Презентацию
                </Button>
                <Button variant="ghost" size="sm" onClick={() => { if(onChartClick) onChartClick("Отправь этот отчет на почту") }} className="flex items-center gap-1.5 h-8 px-2.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors shadow-sm hidden lg:flex">
                  <Mail className="w-3 h-3" /> На Почту
                </Button>
              </>
            )}
            
            {(!isPinnedView && !isModal) && (
              <Button variant="ghost" size="sm" onClick={() => setIsExpanded(true)} className="flex items-center gap-1.5 h-8 px-2.5 text-xs font-medium text-white bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded transition-colors shadow-sm ml-2">
                <Maximize className="w-3 h-3" /> На весь экран
              </Button>
            )}
            {isModal && (
              <Button variant="ghost" size="sm" onClick={() => setIsExpanded(false)} className="flex items-center justify-center h-8 w-8 p-0 text-slate-400 hover:text-rose-400 bg-slate-800 hover:bg-rose-400/10 border border-slate-700 rounded transition-colors shadow-sm ml-2">
                <X className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>
      );

      return (
        <>
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
              "w-full flex flex-col premium-glass rounded-2xl shadow-xl overflow-hidden group",
              isPinnedView ? "h-full max-w-full cursor-pointer hover:border-primary/40 transition-colors border border-transparent hover:shadow-primary/5" : "max-w-4xl my-4"
            )}
            onClick={() => { if(isPinnedView) setIsExpanded(true); }}
          >
            {title && renderHeader(false)}
            <div className={cn("relative z-0 flex-1 min-h-0 flex flex-col", isPinnedView ? "p-3 pb-1" : "p-6")} ref={chartRef}>
              {renderChart(false)}
            </div>
            
            <AnimatePresence>
              {contextMenu && (
                <>
                  <div className="fixed inset-0 z-40" onClick={closeContextMenu} />
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    transition={{ duration: 0.15 }}
                    style={{ 
                      top: '50%', 
                      left: '50%',
                      transform: 'translate(-50%, -50%)'
                    }}
                    className="fixed z-[9999] bg-slate-900 border border-slate-700 rounded shadow-2xl p-2 min-w-[250px]"
                  >
                    <div className="px-3 py-2 border-b border-slate-800 mb-2 bg-slate-950/50 rounded-sm">
                      <p className="text-xs font-semibold text-slate-400 uppercase">{contextMenu.key}</p>
                      {typeof contextMenu.value === 'object' && contextMenu.value !== null ? (
                        <div className="mt-2 space-y-1">
                          {Object.entries(contextMenu.value).filter(([k]) => !['name', 'color', 'payload', 'cx', 'cy'].includes(k)).slice(0, 5).map(([k, v]) => (
                            <div key={k} className="flex justify-between text-xs gap-4 border-b border-slate-800/50 pb-1 last:border-0">
                              <span className="text-slate-400">{translateCol(k)}</span>
                              <span className="text-white font-medium">{typeof v === 'number' ? v.toLocaleString('ru-RU') : String(v)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm font-bold text-white truncate max-w-[230px]">{String(contextMenu.value)}</p>
                      )}
                    </div>
                    <Button 
                      variant="ghost" 
                      className="w-full justify-start text-sm text-slate-300 hover:text-white hover:bg-slate-800 h-9"
                      onClick={() => { 
                        const rawVal = contextMenu.value;
                        // вытаскиваем строку из объекта (например, когда кликнули по сектору pie-чарта)
                        const strVal = typeof rawVal === 'object' && rawVal !== null 
                          ? String(rawVal.name || rawVal.label || rawVal[contextMenu.key] || JSON.stringify(rawVal))
                          : String(rawVal);
                        const keyLabel = contextMenu.key === 'tax_type' ? 'виду налога' 
                          : contextMenu.key === 'period' ? 'периоду'
                          : contextMenu.key === 'region' ? 'региону'
                          : contextMenu.key;
                        if(onChartClick) onChartClick(
                          `Детализация: покажи подробный анализ данных только для ${keyLabel} = "${strVal}". Разбей по всем доступным измерениям. Покажи динамику, структуру и аномалии.`,
                          { key: contextMenu.key, value: strVal, action: 'drilldown' }
                        );
                        closeContextMenu();
                      }}
                    >
                      <Info className="w-4 h-4 mr-2 text-primary" /> Детали (детализация)
                    </Button>
                    <Button 
                      variant="ghost" 
                      className="w-full justify-start text-sm text-slate-300 hover:text-white hover:bg-slate-800 h-9"
                      onClick={() => { 
                        const rawVal = contextMenu.value;
                        const strVal = typeof rawVal === 'object' && rawVal !== null 
                          ? String(rawVal.name || rawVal.label || rawVal[contextMenu.key] || JSON.stringify(rawVal))
                          : String(rawVal);
                        if(onChartClick) onChartClick(
                          `Сравни показатели для ${contextMenu.key} = "${strVal}" со всеми остальными значениями этого измерения. Выведи сравнительный график.`,
                          { key: contextMenu.key, value: strVal, action: 'compare' }
                        );
                        closeContextMenu();
                      }}
                    >
                      <GitCompare className="w-4 h-4 mr-2 text-accent" /> Сравнить с другими
                    </Button>
                    <Button 
                      variant="ghost" 
                      className="w-full justify-start text-sm text-slate-300 hover:text-white hover:bg-slate-800 h-9"
                      onClick={() => { 
                        const rawVal = contextMenu.value;
                        const strVal = typeof rawVal === 'object' && rawVal !== null 
                          ? String(rawVal.name || rawVal.label || rawVal[contextMenu.key] || JSON.stringify(rawVal))
                          : String(rawVal);
                        if(onChartClick) onChartClick(
                          `Покажи полную таблицу всех сырых данных только для ${contextMenu.key} = "${strVal}".`,
                          { key: contextMenu.key, value: strVal, action: 'raw_data' }
                        );
                        closeContextMenu();
                      }}
                    >
                      <Database className="w-4 h-4 mr-2 text-emerald-400" /> Исходные данные
                    </Button>
                  </motion.div>

                </>
              )}
            </AnimatePresence>
          </motion.div>

          {createPortal(
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-10 bg-slate-950/80 backdrop-blur-md"
                >
                  <div className="absolute inset-0 z-0" onClick={() => setIsExpanded(false)} />
                  <motion.div
                    initial={{ scale: 0.95, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0.95, opacity: 0 }}
                    className="relative z-10 w-full max-w-7xl h-[85vh] flex flex-col premium-glass border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
                    onClick={e => e.stopPropagation()}
                  >
                    {title && renderHeader(true)}
                    <div className="p-8 flex-1 flex flex-col relative z-0 min-h-0" ref={expandedChartRef}>
                      {renderChart(true)}
                    </div>
                  </motion.div>
                </motion.div>
              )}
            </AnimatePresence>,
            document.body
          )}
        </>
      );
    }
    
    return (
      <div className="my-4 group">
        <div className="premium-glass rounded-2xl overflow-hidden shadow-xl">
          <div className="px-4 py-3 bg-slate-800/50 border-b border-white/5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TableProperties className="w-4 h-4 text-slate-400" />
              <span className="font-mono text-xs text-slate-300 uppercase tracking-wider">Raw JSON Data</span>
            </div>
          </div>
          <div className="p-4 overflow-x-auto custom-scrollbar">
            <pre className="text-primary font-mono text-xs leading-relaxed">
              {JSON.stringify(parsed, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    );
  } catch {
    return <div className="whitespace-pre-wrap leading-relaxed text-slate-200">{content}</div>;
  }
};
