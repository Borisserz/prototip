import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Save, RefreshCw, Bot, Check, AlertCircle, Loader2 } from 'lucide-react';

const API = 'http://localhost:8000';

type AgentCfg = { role: string; goal: string; rules: string; few_shot?: string };

/**
 * Центр управления промптами (Phase 3).
 * Читает agents.yaml через /api/v1/admin/prompts и позволяет редактировать
 * промпты агентов на лету (PUT). Изменения подхватываются графом без рестарта.
 */
export const PromptsAdmin: React.FC = () => {
  const [agents, setAgents] = useState<Record<string, AgentCfg>>({});
  const [selected, setSelected] = useState<string>('');
  const [draft, setDraft] = useState<AgentCfg>({ role: '', goal: '', rules: '', few_shot: '' });
  const [status, setStatus] = useState<'idle' | 'loading' | 'saving' | 'saved' | 'error'>('idle');
  const [error, setError] = useState<string>('');

  const load = async () => {
    setStatus('loading');
    setError('');
    try {
      const res = await fetch(`${API}/api/v1/admin/prompts`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const ag = data.agents || {};
      setAgents(ag);
      const first = selected && ag[selected] ? selected : Object.keys(ag)[0] || '';
      setSelected(first);
      if (first) setDraft({ few_shot: '', ...ag[first] });
      setStatus('idle');
    } catch (e: any) {
      setError(String(e?.message || e));
      setStatus('error');
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pick = (name: string) => {
    setSelected(name);
    setDraft({ few_shot: '', ...agents[name] });
    setStatus('idle');
    setError('');
  };

  const save = async () => {
    if (!selected) return;
    setStatus('saving');
    setError('');
    try {
      const res = await fetch(`${API}/api/v1/admin/prompts/${selected}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setAgents((prev) => ({ ...prev, [selected]: data.config }));
      setStatus('saved');
      setTimeout(() => setStatus('idle'), 2500);
    } catch (e: any) {
      setError(String(e?.message || e));
      setStatus('error');
    }
  };

  const field = (label: string, key: keyof AgentCfg, rows = 2) => (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</label>
      <textarea
        rows={rows}
        value={(draft[key] as string) || ''}
        onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
        className="w-full bg-slate-800/70 border border-slate-700 rounded-lg p-3 text-sm text-slate-200 focus:border-primary focus:outline-none resize-y font-mono"
      />
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
          <Bot className="w-4 h-4" /> Центр управления промптами
        </h3>
        <Button variant="ghost" size="sm" onClick={load} className="text-slate-400 hover:text-white">
          <RefreshCw className="w-4 h-4 mr-2" /> Обновить
        </Button>
      </div>

      <p className="text-xs text-slate-500">
        Промпты хранятся в <code>app/config/agents.yaml</code>. Изменения применяются на лету —
        граф LangGraph подхватывает их без перезапуска кода.
      </p>

      {status === 'loading' && (
        <div className="flex items-center gap-2 text-slate-400 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Загрузка…</div>
      )}

      <div className="flex flex-col md:flex-row gap-4">
        {/* список агентов */}
        <div className="md:w-56 flex md:flex-col gap-1 flex-wrap">
          {Object.keys(agents).map((name) => (
            <button
              key={name}
              onClick={() => pick(name)}
              className={`text-left text-sm px-3 py-2 rounded-lg transition-colors ${
                selected === name ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
              }`}
            >
              {name}
            </button>
          ))}
        </div>

        {/* редактор */}
        <div className="flex-1 space-y-3 min-w-0">
          {selected ? (
            <>
              {field('Role (роль)', 'role', 2)}
              {field('Goal (цель)', 'goal', 2)}
              {field('Rules (правила)', 'rules', 8)}
              {field('Few-shot (примеры)', 'few_shot', 5)}

              <div className="flex items-center gap-3 pt-1">
                <Button
                  onClick={save}
                  disabled={status === 'saving'}
                  className={`min-w-[140px] ${status === 'saved' ? 'bg-emerald-600 hover:bg-emerald-600' : 'bg-primary hover:bg-primary/90'} text-white`}
                >
                  {status === 'saving' && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  {status === 'saved' && <Check className="w-4 h-4 mr-2" />}
                  {status !== 'saving' && status !== 'saved' && <Save className="w-4 h-4 mr-2" />}
                  {status === 'saving' ? 'Сохранение…' : status === 'saved' ? 'Сохранено!' : 'Сохранить'}
                </Button>
                {error && (
                  <span className="flex items-center gap-1 text-rose-400 text-xs">
                    <AlertCircle className="w-4 h-4" /> {error}
                  </span>
                )}
              </div>
            </>
          ) : (
            <p className="text-slate-500 text-sm">Нет доступных агентов.</p>
          )}
        </div>
      </div>
    </div>
  );
};
