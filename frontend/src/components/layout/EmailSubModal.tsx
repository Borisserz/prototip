import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Mail, Send, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from "@/components/ui/button";
import { API_BASE } from "@/lib/config";

interface EmailSubModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const EmailSubModal: React.FC<EmailSubModalProps> = ({ isOpen, onClose }) => {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubscribe = async () => {
    if (!email) return;
    setIsLoading(true);
    setStatus('idle');
    
    try {
      const res = await fetch(`${API_BASE}/api/v1/send-email`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          to: email,
          subject: "Подписка на дашборд",
          content: "Вы успешно подписались на еженедельную рассылку отчетов."
        })
      });
      
      const data = await res.json();
      if (res.ok) {
        setStatus('success');
        setMessage(data.message || 'Подписка оформлена!');
      } else {
        setStatus('error');
        setMessage(data.detail || 'Ошибка подписки.');
      }
    } catch (e: any) {
      setStatus('error');
      setMessage('Сетевая ошибка при отправке запроса.');
    } finally {
      setIsLoading(false);
      setEmail('');
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-md"
          >
            <div className="bg-slate-900 border border-slate-700/50 rounded-2xl shadow-2xl overflow-hidden glass-panel">
              <div className="p-6 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
                <h2 className="text-xl font-semibold text-white flex items-center gap-2">
                  <Mail className="w-5 h-5 text-primary" /> 
                  Отчеты на почту
                </h2>
                <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              
              <div className="p-6 space-y-6">
                <p className="text-sm text-slate-300 leading-relaxed">
                  Подпишитесь на автоматическую отправку агрегированных отчетов и презентаций на ваш Email. Отчеты формируются еженедельно.
                </p>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-400 mb-1">Ваш Email</label>
                    <input 
                      type="email" 
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="analyst@tax.gov.by"
                      className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors"
                    />
                  </div>
                </div>

                {status === 'success' && (
                  <div className="flex items-start gap-3 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400">
                    <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
                    <p className="text-sm">{message}</p>
                  </div>
                )}
                
                {status === 'error' && (
                  <div className="flex items-start gap-3 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400">
                    <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                    <p className="text-sm">{message}</p>
                  </div>
                )}
                
                <Button 
                  onClick={handleSubscribe} 
                  disabled={!email || isLoading}
                  className="w-full h-12 bg-primary hover:bg-primary/90 text-white font-medium rounded-xl shadow-lg shadow-primary/20 transition-all disabled:opacity-50"
                >
                  {isLoading ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Подписка...</>
                  ) : (
                    <><Send className="w-4 h-4 mr-2" /> Подписаться</>
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};