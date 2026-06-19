import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Brain, Save, Check, Loader2, History, User } from 'lucide-react';
import { Button } from '@/components/ui/button';

const API_BASE = 'http://localhost:8000';

interface HistoryItem {
  prompt: string;
  response: string;
  ts: string;
}

/** Phase 4: управление долгосрочной памятью — профиль пользователя + история чата. */
export const MemoryAdmin: React.FC = () => {
  const [profile, setProfile] = useState('');
  const [role, setRole] = useState('');
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'done'>('idle');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const authHeaders = (): Record<string, string> => {
    const token = localStorage.getItem('jwt_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [pRes, hRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/memory/profile`, { headers: authHeaders() }),
        fetch(`${API_BASE}/api/v1/memory/history?limit=20`, { headers: authHeaders() }),
      ]);
      if (pRes.ok) {
        const p = await pRes.json();
        setProfile(p.profile || '');
        setRole(p.role || '');
      }
      if (hRes.ok) {
        const h = await hRes.json();
        setHistory(h.history || []);
      }
    } catch (e: any) {
      setError(e?.message || 'Не удалось загрузить память');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    setSaveState('saving');
    try {
      const res = await fetch(`${API_BASE}/api/v1/memory/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ profile, role }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSaveState('done');
      setTimeout(() => setSaveState('idle'), 2500);
    } catch (e: any) {
      setError(e?.message || 'Не удалось сохранить профиль');
      setSaveState('idle');
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="flex items-center gap-2">
        <Brain className="w-5 h-5 text-violet-400" />
        <div>
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Долгосрочная память</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Профиль и история обогащают System Prompt перед генерацией SQL (RAG за неделю).
          </p>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-300 text-sm">{error}</div>
      )}

      {/* Профиль */}
      <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 space-y-3">
        <div className="flex items-center gap-2 text-slate-300">
          <User className="w-4 h-4" />
          <span className="text-sm font-medium">Профиль пользователя</span>
        </div>
        <input
          value={role}
          onChange={(e) => setRole(e.target.value)}
          placeholder="Роль / должность (например: бухгалтер)"
          className="w-full bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-violet-500/50 focus:outline-none"
        />
        <textarea
          value={profile}
          onChange={(e) => setProfile(e.target.value)}
          rows={4}
          placeholder="Кто пользователь и чем занимается. Например: «Бухгалтер, отвечает за налоговую отчётность по РБ, чаще всего смотрит данные по налогам и задолженностям»."
          className="w-full bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-violet-500/50 focus:outline-none resize-y"
        />
        <div className="flex justify-end">
          <Button
            onClick={save}
            disabled={saveState !== 'idle'}
            className={`min-w-[140px] ${
              saveState === 'done'
                ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                : 'bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30'
            }`}
          >
            {saveState === 'saving' && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {saveState === 'done' && <Check className="w-4 h-4 mr-2" />}
            {saveState === 'idle' && <Save className="w-4 h-4 mr-2" />}
            {saveState === 'saving' ? 'Сохранение…' : saveState === 'done' ? 'Сохранено!' : 'Сохранить профиль'}
          </Button>
        </div>
      </div>

      {/* История */}
      <div>
        <div className="flex items-center gap-2 mb-3 text-slate-300">
          <History className="w-4 h-4" />
          <span className="text-sm font-medium">Недавняя история ({history.length})</span>
        </div>
        {loading ? (
          <div className="text-slate-500 text-sm">Загрузка…</div>
        ) : history.length === 0 ? (
          <div className="text-slate-500 text-sm">История пуста — задайте вопрос в чате.</div>
        ) : (
          <div className="space-y-2 max-h-[40vh] overflow-y-auto pr-1">
            {history.map((h, idx) => (
              <div key={idx} className="p-3 rounded-lg bg-slate-900 border border-slate-700/50">
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span className="truncate">{h.ts}</span>
                </div>
                <p className="text-sm text-slate-200">{h.prompt}</p>
                {h.response && (
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">{h.response}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
};
