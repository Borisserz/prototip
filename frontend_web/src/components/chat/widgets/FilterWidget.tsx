import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Filter, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useChatStore } from '@/store/useChatStore';

interface FilterWidgetProps {
  regionOptions?: string[];
  taxOptions?: string[];
  onApply: (filters: { region: string, tax_type: string }) => void;
}

export const FilterWidget: React.FC<FilterWidgetProps> = ({ 
  regionOptions = ['Все регионы', 'г. Минск', 'Брестская область', 'Витебская область', 'Гомельская область', 'Гродненская область', 'Минская область', 'Могилевская область'],
  taxOptions = ['Все налоги', 'НДС', 'Налог на прибыль', 'Подоходный налог', 'Акцизы', 'Имущественные налоги'],
  onApply
}) => {
  const [region, setRegion] = useState(regionOptions[0]);
  const [tax, setTax] = useState(taxOptions[0]);
  const addMessage = useChatStore(state => state.addMessage);

  const handleApply = () => {
    onApply({ region, tax_type: tax });
    const query = `Покажи данные: Регион = ${region}, Налог = ${tax}`;
    addMessage({ role: 'user', content: query });
    // In a real app, this should also trigger the socket send.
    // For now we just add it to the UI.
  };

  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="mt-4 p-4 rounded-xl border border-slate-700/50 bg-slate-800/80 shadow-lg w-full max-w-sm"
    >
      <div className="flex items-center gap-2 mb-4">
        <Filter className="w-5 h-5 text-primary" />
        <h4 className="text-sm font-semibold text-white">Интерактивный фильтр</h4>
      </div>
      
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Регион</label>
          <select 
            className="w-full bg-slate-900 border border-slate-700 rounded-md p-2 text-sm text-white focus:outline-none focus:border-primary"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          >
            {regionOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
          </select>
        </div>
        
        <div>
          <label className="block text-xs text-slate-400 mb-1">Вид налога</label>
          <select 
            className="w-full bg-slate-900 border border-slate-700 rounded-md p-2 text-sm text-white focus:outline-none focus:border-primary"
            value={tax}
            onChange={(e) => setTax(e.target.value)}
          >
            {taxOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
          </select>
        </div>
        
        <Button 
          onClick={handleApply}
          className="w-full bg-primary hover:bg-primary/90 text-white mt-2 flex items-center justify-center gap-2"
        >
          <Play className="w-4 h-4" /> Применить фильтры
        </Button>
      </div>
    </motion.div>
  );
};
