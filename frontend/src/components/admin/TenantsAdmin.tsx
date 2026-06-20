import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Building2, Plus, Trash2, KeyRound, Copy, Check, Loader2, Database } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { API_BASE } from "@/lib/config";

interface Tenant {
  client_id: string;
  name: string;
  clickhouse: { host: string; port: number; database: string; user: string };
  vector_collection: string;
  allowed_tables: string[];
  enforce_client_id: boolean;
  active: boolean;
  created_at: string;
}

/** Phase 6: Админ-панель клиентов (B2B multi-tenant). */
export const TenantsAdmin: React.FC = () => {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [newToken, setNewToken] = useState<{ id: string; jwt: string; api: string } | null>(null);

  const [form, setForm] = useState({
    client_id: '', name: '', ch_host: 'localhost', ch_port: 8201,
    ch_database: '', ch_password: '', allowed_tables: '', enforce_client_id: true,
  });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/tenants`);
      const data = await res.json();
      setTenants(data.tenants || []);
    } catch (e: any) {
      setError(e?.message || 'Ошибка загрузки клиентов');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.client_id || !form.name) {
      setError('Заполните client_id и название');
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/tenants`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: form.client_id,
          name: form.name,
          ch_host: form.ch_host,
          ch_port: Number(form.ch_port),
          ch_database: form.ch_database || `tenant_${form.client_id}`,
          ch_password: form.ch_password,
          allowed_tables: form.allowed_tables.split(',').map((s) => s.trim()).filter(Boolean),
          enforce_client_id: form.enforce_client_id,
        }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || `HTTP ${res.status}`);
      }
      const t = await res.json();
      setNewToken({ id: t.client_id, jwt: t.jwt_token, api: t.api_key });
      setForm({ ...form, client_id: '', name: '', ch_password: '', allowed_tables: '' });
      await load();
    } catch (e: any) {
      setError(e?.message || 'Не удалось создать клиента');
    } finally {
      setCreating(false);
    }
  };

  const rotate = async (id: string) => {
    const res = await fetch(`${API_BASE}/api/v1/admin/tenants/${id}/rotate-token`, { method: 'POST' });
    if (res.ok) {
      const t = await res.json();
      setNewToken({ id, jwt: t.jwt_token, api: t.api_key });
    }
  };

  const remove = async (id: string) => {
    await fetch(`${API_BASE}/api/v1/admin/tenants/${id}`, { method: 'DELETE' });
    await load();
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard?.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="flex items-center gap-2">
        <Building2 className="w-5 h-5 text-sky-400" />
        <div>
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Клиенты (B2B)</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Изолированные клиенты: личный ClickHouse, коллекция семантики, уникальный JWT-токен.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-300 text-sm">{error}</div>
      )}

      {/* Новый токен после создания/ротации */}
      {newToken && (
        <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 space-y-2">
          <p className="text-sm text-emerald-300 font-medium">Токены клиента «{newToken.id}» (скопируйте — JWT показывается один раз):</p>
          {([['JWT', newToken.jwt], ['API-ключ', newToken.api]] as const).map(([label, val]) => (
            <div key={label} className="flex items-center gap-2">
              <span className="text-xs text-slate-400 w-16">{label}</span>
              <code className="flex-1 text-xs text-slate-200 bg-slate-950/60 rounded px-2 py-1 truncate">{val}</code>
              <Button size="sm" variant="ghost" onClick={() => copy(val, label)} className="text-slate-300">
                {copied === label ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Форма создания */}
      <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 space-y-3">
        <div className="flex items-center gap-2 text-slate-300">
          <Plus className="w-4 h-4" />
          <span className="text-sm font-medium">Создать клиента</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}
            placeholder="client_id (напр. pivzavod)"
            className="bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none" />
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Название (напр. Пивзавод)"
            className="bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none" />
          <input value={form.ch_host} onChange={(e) => setForm({ ...form, ch_host: e.target.value })}
            placeholder="ClickHouse host"
            className="bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none" />
          <input type="number" value={form.ch_port} onChange={(e) => setForm({ ...form, ch_port: Number(e.target.value) })}
            placeholder="ClickHouse port"
            className="bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none" />
          <input value={form.ch_password} onChange={(e) => setForm({ ...form, ch_password: e.target.value })}
            placeholder="ClickHouse password" type="password"
            className="bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none" />
          <input value={form.allowed_tables} onChange={(e) => setForm({ ...form, allowed_tables: e.target.value })}
            placeholder="Разрешённые таблицы через запятую"
            className="bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none" />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={form.enforce_client_id}
            onChange={(e) => setForm({ ...form, enforce_client_id: e.target.checked })} />
          Жёстко добавлять <code className="text-xs">WHERE client_id = …</code> (row-isolation)
        </label>
        <div className="flex justify-end">
          <Button onClick={create} disabled={creating}
            className="bg-sky-500/15 hover:bg-sky-500/25 text-sky-200 border border-sky-500/30">
            {creating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
            Создать
          </Button>
        </div>
      </div>

      {/* Список клиентов */}
      <div>
        <h4 className="text-xs uppercase tracking-wider text-slate-500 font-bold mb-3">Клиенты ({tenants.length})</h4>
        {loading ? (
          <div className="text-slate-500 text-sm">Загрузка…</div>
        ) : tenants.length === 0 ? (
          <div className="text-slate-500 text-sm">Клиентов пока нет.</div>
        ) : (
          <div className="space-y-2">
            {tenants.map((t) => (
              <div key={t.client_id} className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-white">{t.name} <span className="text-slate-500 text-sm">({t.client_id})</span></p>
                    <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                      <Database className="w-3 h-3" /> {t.clickhouse.host}:{t.clickhouse.port}/{t.clickhouse.database}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      Таблицы: {t.allowed_tables.length ? t.allowed_tables.join(', ') : '—'}
                      {t.enforce_client_id && <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">row-isolation</span>}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Button size="sm" variant="ghost" onClick={() => rotate(t.client_id)} className="text-slate-300" title="Перевыпустить токен">
                      <KeyRound className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => remove(t.client_id)} className="text-rose-400 hover:bg-rose-500/10" title="Удалить">
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
};