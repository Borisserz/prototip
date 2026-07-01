import React from 'react';
import { motion } from 'framer-motion';
import { User, LogOut, Database, ChevronLeft, Shield, CheckCircle2, ServerCrash } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useChatStore } from '../../store/useChatStore';
import { cn } from '@/App';

interface UserProfileProps {
  username: string;
  wsConnected: boolean;
  onBack: () => void;
  handleLogout: () => void;
}

export const UserProfile: React.FC<UserProfileProps> = ({ username, wsConnected, onBack, handleLogout }) => {
  const isAnalystMode = useChatStore((state) => state.isAnalystMode);
  const setAnalystMode = useChatStore((state) => state.setAnalystMode);

  return (
    <div className="h-full flex flex-col items-center justify-center p-8 bg-slate-950/20">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="w-full max-w-2xl bg-slate-800/50 backdrop-blur-xl border border-white/10 rounded-3xl p-8 shadow-2xl relative overflow-hidden"
      >
        {/* Decorator blob */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none" />

        <Button 
          variant="ghost" 
          onClick={onBack} 
          className="absolute top-6 left-6 text-slate-400 hover:text-white"
        >
          <ChevronLeft className="w-5 h-5 mr-1" /> Вернуться
        </Button>

        <div className="flex flex-col items-center mt-8 mb-10">
          <div className="w-24 h-24 rounded-full bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(56,189,248,0.15)] relative">
            <User className="w-12 h-12 text-primary" />
            <div className={cn(
              "absolute bottom-1 right-1 w-5 h-5 rounded-full border-4 border-slate-800 flex items-center justify-center shadow-lg",
              wsConnected ? "bg-emerald-500" : "bg-rose-500"
            )}>
              <div className="w-full h-full rounded-full animate-ping opacity-50 bg-current"></div>
            </div>
          </div>
          <h2 className="text-3xl font-bold text-white tracking-tight mb-2 flex items-center gap-2">
            {username}
            {username === 'FederalAnalyst' && <Shield className="w-5 h-5 text-amber-400" />}
          </h2>
          <div className="flex items-center gap-2 text-sm text-slate-400">
            {wsConnected ? (
              <span className="flex items-center gap-1.5 text-emerald-400"><CheckCircle2 className="w-4 h-4" /> Платформа подключена</span>
            ) : (
              <span className="flex items-center gap-1.5 text-rose-400"><ServerCrash className="w-4 h-4" /> Потеряно соединение с сервером</span>
            )}
          </div>
        </div>

        <div className="space-y-6">
          {/* Settings Section */}
          <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-700/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className={cn(
                "p-3 rounded-xl transition-colors",
                isAnalystMode ? "bg-primary/20 text-primary shadow-[0_0_15px_rgba(56,189,248,0.2)]" : "bg-slate-800 text-slate-400"
              )}>
                <Database className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white mb-1">Режим Аналитика</h3>
                <p className="text-sm text-slate-400 max-w-sm leading-relaxed">
                  Отображать техническую информацию в чате (сырые SQL запросы ClickHouse, генерируемые нейросетью).
                </p>
              </div>
            </div>
            
            <button
              onClick={() => setAnalystMode(!isAnalystMode)}
              className={cn(
                "relative inline-flex h-8 w-14 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900",
                isAnalystMode ? "bg-primary" : "bg-slate-700"
              )}
            >
              <span
                className={cn(
                  "pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                  isAnalystMode ? "translate-x-6" : "translate-x-0"
                )}
              />
            </button>
          </div>

          {/* Logout Section */}
          <div className="pt-6 border-t border-slate-700/50 flex justify-end">
            <Button 
              variant="outline" 
              onClick={handleLogout}
              className="border-rose-500/30 text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 transition-colors"
            >
              <LogOut className="w-4 h-4 mr-2" /> Выйти из аккаунта
            </Button>
          </div>
        </div>

      </motion.div>
    </div>
  );
};
