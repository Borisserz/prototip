import React from 'react';
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { GripHorizontal, Pin, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DynamicChart } from "../chat/DynamicChart";
import { ExecutiveSummary } from "./ExecutiveSummary";
import { AutoInsights } from "./AutoInsights";

const ResponsiveGridLayout = WidthProvider(Responsive);

interface DashboardGridProps {
  pinnedCharts: string[];
  layouts: any[];
  setLayouts: (newLayout: any[]) => void;
  setPinnedCharts: (charts: string[]) => void;
}

export const DashboardGrid: React.FC<DashboardGridProps> = ({ pinnedCharts, layouts, setLayouts, setPinnedCharts }) => {
  return (
    <div className="flex flex-col gap-6 w-full">
      {/* Executive Summary (KPIs) */}
      <ExecutiveSummary />

      {/* Auto-Insights */}
      <AutoInsights />

      {pinnedCharts.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center text-slate-500 space-y-4 rounded-2xl border-2 border-dashed border-white/10 bg-slate-900/40 backdrop-blur-xl relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>
          <div className="w-16 h-16 rounded-full bg-slate-800/80 flex items-center justify-center shadow-[inset_0_2px_10px_rgba(0,0,0,0.5)] border border-white/5 group-hover:scale-110 transition-transform duration-500 relative">
            <div className="absolute inset-0 rounded-full border border-teal-500/30 animate-[ping_3s_infinite] opacity-50"></div>
            <Pin className="w-7 h-7 text-teal-400/70 group-hover:text-teal-400 transition-colors drop-shadow-[0_0_8px_rgba(45,212,191,0.5)]" />
          </div>
          <div className="text-center relative z-10">
            <h3 className="text-sm font-bold text-transparent bg-clip-text bg-gradient-to-r from-slate-200 to-slate-400">Нет закрепленных графиков</h3>
            <p className="text-xs max-w-[250px] mt-2 text-slate-400 leading-relaxed group-hover:text-slate-300 transition-colors">Сгенерируйте график в чате и нажмите кнопку <strong className="text-teal-400 font-medium">Pin</strong>, чтобы он появился здесь.</p>
          </div>
        </div>
      ) : (
        <ResponsiveGridLayout
          className="layout"
          layouts={{ lg: layouts }}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
          cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
          rowHeight={380}
          onLayoutChange={(currentLayout: any) => setLayouts(currentLayout)}
          draggableHandle=".drag-handle"
        >
          {pinnedCharts.map((chartContent, idx) => {
            const layoutItem = layouts.find(l => l.i === chartContent) || { i: chartContent, x: (idx % 2) * 6, y: Math.floor(idx / 2), w: 6, h: 1 };
            return (
              <div key={chartContent} data-grid={layoutItem} className="relative group h-full">
                <div className="absolute inset-0 premium-glass rounded-2xl border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.4)] hover:shadow-[0_8px_40px_rgba(45,212,191,0.15)] hover:border-white/20 transition-all duration-500 overflow-hidden">
                  <div className="drag-handle absolute top-4 left-4 z-20 w-8 h-8 flex items-center justify-center cursor-move opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900/80 backdrop-blur-md rounded-lg border border-white/10 hover:bg-slate-800 shadow-md" title="Потяните, чтобы переместить">
                    <GripHorizontal className="w-4 h-4 text-slate-300" />
                  </div>
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="absolute top-4 right-4 z-20 w-8 h-8 rounded-md opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900/80 hover:bg-rose-500/20 hover:border-rose-500/50 hover:text-rose-400 backdrop-blur-md border border-white/10 shadow-md"
                    onClick={() => {
                      setPinnedCharts(pinnedCharts.filter(c => c !== chartContent));
                      setLayouts(layouts.filter(item => item.i !== chartContent));
                    }}
                  >
                    <X className="w-4 h-4 text-slate-400" />
                  </Button>
                  <div className="h-full w-full p-1">
                    <DynamicChart content={chartContent} isPinnedView={true} />
                  </div>
                </div>
              </div>
            );
          })}
        </ResponsiveGridLayout>
      )}
    </div>
  );
};
