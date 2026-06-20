import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Sparkles, Send, Loader2, Trash2, CheckCircle2, ChevronLeft, CalendarClock, Settings2, Power, Clock, Calendar, FileText, Eye, Check, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useChatStore } from '../../store/useChatStore';

interface SubscriptionsViewProps {
  onBackToChat: () => void;
}

export const SubscriptionsView: React.FC<SubscriptionsViewProps> = ({ onBackToChat }) => {
  const verifiedEmail = useChatStore(state => state.verifiedEmail);
  const setVerifiedEmail = useChatStore(state => state.setVerifiedEmail);
  const token = localStorage.getItem('access_token');

  const [emailInput, setEmailInput] = useState('');
  const [subs, setSubs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Form State
  const [frequency, setFrequency] = useState('daily');
  const [hour, setHour] = useState('09');
  const [minute, setMinute] = useState('00');
  const [aiPrompt, setAiPrompt] = useState('');
  
  // Dropdown States
  const [isFreqOpen, setIsFreqOpen] = useState(false);
  const [isHourOpen, setIsHourOpen] = useState(false);
  const [isMinOpen, setIsMinOpen] = useState(false);

  const frequencies = [
    { id: 'daily', label: 'Каждый день', desc: 'Ежедневная сводка' },
    { id: 'weekly', label: 'Раз в неделю (Пн)', desc: 'Отчет за неделю' },
    { id: 'monthly', label: 'Раз в месяц (1-го)', desc: 'Отчет за месяц' },
    { id: 'quarterly', label: 'Раз в квартал', desc: 'Сводка за квартал' }
  ];

  const hours = Array.from({length: 24}, (_, i) => i.toString().padStart(2, '0'));
  const minutes = Array.from({length: 60}, (_, i) => i.toString().padStart(2, '0'));


  // Preview State
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (verifiedEmail) {
      fetchSubs();
    }
  }, [verifiedEmail]);

  const fetchSubs = async () => {
    try {
      setLoading(true);
      const res = await fetch('http://localhost:8000/api/v1/subscriptions', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.subscriptions) {
        setSubs(data.subscriptions.filter((s: any) => s.email === verifiedEmail));
      }
    } catch (e) {
      console.error("Failed to fetch subscriptions", e);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyEmail = (e: React.FormEvent) => {
    e.preventDefault();
    if (emailInput.includes('@')) {
      setVerifiedEmail(emailInput);
    }
  };

  const handleGeneratePreview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!aiPrompt.trim() || !verifiedEmail) return;

    setIsGeneratingPreview(true);
    // Имитация работы AI-агента для предпросмотра
    await new Promise(resolve => setTimeout(resolve, 1500));
    setIsGeneratingPreview(false);
    setIsPreviewing(true);
  };

  const getCronString = () => {
    if (frequency === 'daily') return `${minute} ${hour} * * *`;
    if (frequency === 'weekly') return `${minute} ${hour} * * 1`; // Каждый понедельник
    if (frequency === 'monthly') return `${minute} ${hour} 1 * *`; // Каждое 1 число
    if (frequency === 'quarterly') return `${minute} ${hour} 1 1,4,7,10 *`; 
    return `0 9 * * *`;
  };

  const getFreqLabel = () => {
    const f = frequencies.find(f => f.id === frequency);
    return f ? f.label : '';
  }

  const handleSaveSubscription = async () => {
    setIsSaving(true);
    const cron = getCronString();
    
    // Формируем красивое название на основе пользовательских вводов для списка
    const humanTitle = `${getFreqLabel()} в ${hour}:${minute} — ${aiPrompt}`;

    const newSub = {
      id: Math.random().toString(36).substring(7),
      email: verifiedEmail,
      schedule: cron,
      prompt: humanTitle,
      report_type: "ai_summary"
    };

    try {
      await fetch('http://localhost:8000/api/v1/subscriptions', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(newSub)
      });
      setAiPrompt('');
      setIsPreviewing(false);
      fetchSubs();
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await fetch(`http://localhost:8000/api/v1/subscriptions/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchSubs();
    } catch (e) {
      console.error(e);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await fetch(`http://localhost:8000/api/v1/subscriptions/${id}/toggle`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchSubs();
    } catch (e) {
      console.error(e);
    }
  };

  if (!verifiedEmail) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8">
        <Button variant="ghost" onClick={onBackToChat} className="absolute top-6 left-6 text-slate-400 hover:text-white">
          <ChevronLeft className="w-5 h-5 mr-1" /> Назад
        </Button>
        <motion.div 
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="max-w-md w-full bg-slate-800/50 backdrop-blur-xl border border-white/10 p-8 rounded-3xl shadow-2xl relative overflow-hidden"
        >
          <div className="absolute -top-24 -right-24 w-48 h-48 bg-violet-500/20 rounded-full blur-3xl pointer-events-none" />
          
          <div className="w-16 h-16 rounded-2xl bg-violet-500/20 border border-violet-500/30 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(139,92,246,0.2)]">
            <Mail className="w-8 h-8 text-violet-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Настройка рассылок</h2>
          <p className="text-slate-400 mb-8 leading-relaxed text-sm">
            Введите ваш email, чтобы получать автоматические отчеты и дашборды, сгенерированные нашим ИИ-агентом по вашему расписанию.
          </p>

          <form onSubmit={handleVerifyEmail} className="space-y-4">
            <Input 
              type="email"
              value={emailInput}
              onChange={(e) => setEmailInput(e.target.value)}
              placeholder="name@company.com"
              className="bg-slate-900/50 border-slate-700/50 h-12 text-lg focus-visible:ring-violet-500"
              required
            />
            <Button type="submit" className="w-full h-12 bg-violet-600 hover:bg-violet-500 text-white shadow-lg">
              Продолжить
            </Button>
          </form>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col relative max-w-4xl mx-auto w-full p-6">
      <div className="flex items-center justify-between mb-8 pt-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={onBackToChat} className="text-slate-400 hover:text-white hover:bg-white/10">
            <ChevronLeft className="w-6 h-6" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Mail className="w-6 h-6 text-violet-400" /> Центр Рассылок
            </h1>
            <p className="text-sm text-slate-400 flex items-center gap-2 mt-1">
              Отчеты приходят на <span className="text-emerald-400 font-medium">{verifiedEmail}</span>
              <button onClick={() => setVerifiedEmail(null)} className="text-xs underline hover:text-white transition-colors">изменить</button>
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 pb-10">
        
        {/* Creator Section */}
        <div className="bg-slate-800/40 border border-violet-500/20 rounded-3xl p-6 relative overflow-hidden shadow-[0_0_40px_rgba(139,92,246,0.05)]">
          <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none" />
          
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <Settings2 className="w-5 h-5 text-violet-400" /> Создать новую рассылку
          </h2>

          {!isPreviewing ? (
            <form onSubmit={handleGeneratePreview} className="space-y-6 relative z-10">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div className="space-y-2 relative">
                  <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-violet-400" /> Частота
                  </label>
                  
                  {/* Custom Dropdown */}
                  <div 
                    onClick={() => { setIsFreqOpen(!isFreqOpen); setIsHourOpen(false); setIsMinOpen(false); }}
                    className="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl h-12 px-4 text-white flex items-center justify-between cursor-pointer hover:border-violet-500/50 transition-colors"
                  >
                    <span>{frequencies.find(f => f.id === frequency)?.label}</span>
                    <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isFreqOpen ? 'rotate-180' : ''}`} />
                  </div>
                  
                  <AnimatePresence>
                    {isFreqOpen && (
                      <motion.div 
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="absolute top-[76px] left-0 w-full bg-slate-800 border border-slate-700/50 rounded-xl shadow-2xl z-50 overflow-hidden"
                      >
                        {frequencies.map(f => (
                          <div 
                            key={f.id}
                            onClick={() => { setFrequency(f.id); setIsFreqOpen(false); }}
                            className={`px-4 py-3 cursor-pointer transition-colors ${frequency === f.id ? 'bg-violet-500/20 text-violet-300' : 'hover:bg-slate-700/50 text-slate-200'}`}
                          >
                            <div className="font-medium">{f.label}</div>
                            <div className="text-xs text-slate-400 mt-0.5">{f.desc}</div>
                          </div>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
                
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                    <Clock className="w-4 h-4 text-violet-400" /> Время отправки (24ч)
                  </label>
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <div 
                        onClick={() => { setIsHourOpen(!isHourOpen); setIsFreqOpen(false); setIsMinOpen(false); }}
                        className="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl h-12 px-4 text-white flex items-center justify-between cursor-pointer hover:border-violet-500/50 transition-colors"
                      >
                        <span>{hour}</span>
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      </div>
                      <AnimatePresence>
                        {isHourOpen && (
                          <motion.div 
                            initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                            className="absolute top-[52px] left-0 w-full bg-slate-800 border border-slate-700/50 rounded-xl shadow-2xl z-50 h-48 overflow-y-auto custom-scrollbar"
                          >
                            {hours.map(h => (
                              <div key={h} onClick={() => { setHour(h); setIsHourOpen(false); }} className={`px-4 py-2 cursor-pointer transition-colors text-center ${hour === h ? 'bg-violet-500/20 text-violet-300' : 'hover:bg-slate-700/50 text-slate-200'}`}>
                                {h}
                              </div>
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                    <span className="text-slate-400 font-bold">:</span>
                    <div className="relative flex-1">
                      <div 
                        onClick={() => { setIsMinOpen(!isMinOpen); setIsFreqOpen(false); setIsHourOpen(false); }}
                        className="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl h-12 px-4 text-white flex items-center justify-between cursor-pointer hover:border-violet-500/50 transition-colors"
                      >
                        <span>{minute}</span>
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      </div>
                      <AnimatePresence>
                        {isMinOpen && (
                          <motion.div 
                            initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                            className="absolute top-[52px] left-0 w-full bg-slate-800 border border-slate-700/50 rounded-xl shadow-2xl z-50 h-48 overflow-y-auto custom-scrollbar"
                          >
                            {minutes.map(m => (
                              <div key={m} onClick={() => { setMinute(m); setIsMinOpen(false); }} className={`px-4 py-2 cursor-pointer transition-colors text-center ${minute === m ? 'bg-violet-500/20 text-violet-300' : 'hover:bg-slate-700/50 text-slate-200'}`}>
                                {m}
                              </div>
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-violet-400" /> Содержание отчета
                </label>
                <textarea
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder="Опишите, какие данные должны быть в отчете (например: сводка по налогам за вчера, топ-3 региона по недоимкам...)"
                  className="w-full bg-slate-900/60 border border-slate-700/50 rounded-xl p-4 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-violet-500/50 min-h-[100px] resize-y"
                  required
                />
              </div>

              <div className="flex justify-end pt-2">
                <Button 
                  type="submit" 
                  disabled={!aiPrompt.trim() || isGeneratingPreview}
                  className="bg-violet-600 hover:bg-violet-500 text-white shadow-lg transition-all px-6"
                >
                  {isGeneratingPreview ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Подготовка макета...</>
                  ) : (
                    <><Eye className="w-4 h-4 mr-2" /> Сгенерировать превью</>
                  )}
                </Button>
              </div>
            </form>
          ) : (
            <motion.div 
              initial={{ opacity: 0, scale: 0.98 }} 
              animate={{ opacity: 1, scale: 1 }}
              className="space-y-6 relative z-10"
            >
              <div className="bg-slate-900/80 border border-slate-700/50 rounded-2xl p-6">
                <div className="border-b border-slate-700/50 pb-4 mb-4">
                  <div className="text-sm text-slate-400 mb-1">От: <span className="text-slate-300">Prototip BI &lt;ai@prototip.bi&gt;</span></div>
                  <div className="text-sm text-slate-400 mb-2">Кому: <span className="text-slate-300">{verifiedEmail}</span></div>
                  <div className="text-lg font-semibold text-white">Автоматический отчет: {aiPrompt.substring(0, 40)}{aiPrompt.length > 40 ? '...' : ''}</div>
                </div>
                
                <div className="prose prose-invert prose-sm max-w-none">
                  <p>Здравствуйте!</p>
                  <p>В соответствии с вашей подпиской, направляю актуальные данные по запросу: <i>"{aiPrompt}"</i>.</p>
                  
                  <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 my-4 flex flex-col gap-4 shadow-inner">
                    <h4 className="text-white font-medium text-sm border-b border-slate-700/50 pb-2">Аналитическая сводка</h4>
                    <div className="text-slate-300 text-sm">
                      <p className="mb-2">Основные инсайты по вашему запросу:</p>
                      <ul className="list-disc pl-5 space-y-1 text-slate-400 mb-4">
                        <li>Зафиксирован рост ключевых показателей на 14% по сравнению с прошлым периодом.</li>
                        <li>Лидирующие позиции занимают центральные регионы.</li>
                        <li>Выявлены незначительные отклонения в динамике сборов.</li>
                      </ul>
                    </div>
                    
                    {/* Dummy Chart Visualization */}
                    <div className="h-40 w-full flex items-end gap-2 pt-4 border-t border-slate-700/50">
                      {[40, 70, 45, 90, 65, 30, 85].map((h, i) => (
                        <div key={i} className="flex-1 bg-violet-500/30 rounded-t-sm border-t border-violet-500/50 relative group transition-all hover:bg-violet-500/50" style={{ height: `${h}%` }}>
                          <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-[10px] text-white opacity-0 group-hover:opacity-100 transition-opacity">
                            {h}M
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="flex justify-between text-xs text-slate-500 mt-1 px-1">
                      <span>Пн</span><span>Вс</span>
                    </div>
                  </div>
                  
                  <p className="text-slate-400 text-xs mt-4">
                    Это письмо было сгенерировано ИИ-агентом автоматически.<br/>
                    Расписание: {getFreqLabel()} в {hour}:{minute}
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <Button 
                  type="button" 
                  variant="ghost"
                  onClick={() => setIsPreviewing(false)}
                  className="text-slate-400 hover:text-white"
                  disabled={isSaving}
                >
                  Редактировать
                </Button>
                <Button 
                  onClick={handleSaveSubscription}
                  disabled={isSaving}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg transition-all px-6"
                >
                  {isSaving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Check className="w-4 h-4 mr-2" />}
                  Подтвердить и запустить
                </Button>
              </div>
            </motion.div>
          )}
        </div>

        {/* Active Subscriptions List */}
        <div>
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" /> Активные задачи
          </h2>
          
          {loading && subs.length === 0 ? (
            <div className="flex items-center justify-center p-12">
              <Loader2 className="w-8 h-8 text-slate-500 animate-spin" />
            </div>
          ) : subs.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12 border border-dashed border-slate-700/50 rounded-3xl bg-slate-800/20">
              <Settings2 className="w-10 h-10 text-slate-600 mb-3" />
              <p className="text-slate-400 text-center">У вас пока нет настроенных рассылок.<br/>Настройте вашу первую задачу выше!</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              <AnimatePresence>
                {subs.map(sub => (
                  <motion.div
                    key={sub.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/50 hover:bg-slate-800 transition-colors flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 group"
                  >
                    <div className="flex-1 min-w-0">
                      <h3 className="text-base font-medium text-slate-200 truncate pr-4">{sub.prompt}</h3>
                      <div className="flex items-center gap-4 mt-2">
                        <span className="flex items-center gap-1.5 text-xs text-slate-400 bg-slate-900/50 px-2 py-1 rounded-md border border-slate-700">
                          <CalendarClock className="w-3.5 h-3.5 text-violet-400" /> Cron: {sub.schedule}
                        </span>
                        <span className="flex items-center gap-1.5 text-xs text-slate-400 bg-slate-900/50 px-2 py-1 rounded-md border border-slate-700">
                          <Sparkles className="w-3.5 h-3.5 text-emerald-400" /> AI Отчет
                        </span>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2 shrink-0">
                      <button 
                        onClick={() => handleToggle(sub.id)}
                        className={`p-2 rounded-xl transition-colors border ${
                          sub.active !== false 
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20" 
                            : "bg-slate-800 text-slate-500 border-slate-700 hover:text-slate-300"
                        }`}
                        title={sub.active !== false ? "Приостановить" : "Возобновить"}
                      >
                        <Power className="w-4 h-4" />
                      </button>
                      <button 
                        onClick={() => handleDelete(sub.id)}
                        className="p-2 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:bg-rose-500/20 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                        title="Удалить"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
