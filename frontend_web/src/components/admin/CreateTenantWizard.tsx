import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X, Building2, Database, ShieldCheck, ClipboardCheck, Check, Copy, Loader2,
  ChevronRight, ChevronLeft, PartyPopper, KeyRound, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { adminApi, type CreatedTenant } from "@/lib/adminApi";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

const STEPS = [
  { icon: Building2, title: "Клиент" },
  { icon: Database, title: "ClickHouse" },
  { icon: ShieldCheck, title: "Доступы" },
  { icon: ClipboardCheck, title: "Проверка" },
];

const blank = {
  client_id: "", name: "",
  ch_host: "localhost", ch_port: 8201, ch_database: "", ch_user: "default", ch_password: "",
  vector_collection: "", allowed_tables: "", enforce_client_id: true,
};

const inputCls =
  "w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none";

/** Phase 6 — пошаговый мастер создания нового клиентского блока. */
export const CreateTenantWizard: React.FC<Props> = ({ isOpen, onClose, onCreated }) => {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({ ...blank });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedTenant | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const set = (k: keyof typeof form, v: any) => setForm((f) => ({ ...f, [k]: v }));
  const reset = () => { setStep(0); setForm({ ...blank }); setCreated(null); setError(null); };
  const close = () => { reset(); onClose(); };

  const canNext = () => {
    if (step === 0) return form.client_id.trim() && form.name.trim();
    return true;
  };

  const submit = async () => {
    setCreating(true);
    setError(null);
    try {
      const t = await adminApi.create({
        client_id: form.client_id.trim(),
        name: form.name.trim(),
        ch_host: form.ch_host,
        ch_port: Number(form.ch_port),
        ch_database: form.ch_database || `tenant_${form.client_id.trim()}`,
        ch_user: form.ch_user,
        ch_password: form.ch_password,
        vector_collection: form.vector_collection || undefined,
        allowed_tables: form.allowed_tables.split(",").map((s) => s.trim()).filter(Boolean),
        enforce_client_id: form.enforce_client_id,
      });
      setCreated(t);
    } catch (e: any) {
      setError(e?.message || "Не удалось создать клиента");
    } finally {
      setCreating(false);
    }
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard?.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
        onClick={close}
      >
        <motion.div
          initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
        >
          {/* header */}
          <div className="flex items-center justify-between border-b border-slate-700/50 px-6 py-4">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
              <Building2 className="h-5 w-5 text-sky-400" />
              {created ? "Клиент создан" : "Новый блок клиента"}
            </h2>
            <button onClick={close} className="text-slate-400 hover:text-white"><X className="h-5 w-5" /></button>
          </div>

          {/* SUCCESS */}
          {created ? (
            <div className="space-y-5 p-6">
              <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
                <PartyPopper className="h-6 w-6 text-emerald-400" />
                <div>
                  <p className="font-medium text-emerald-300">«{created.name}» готов к работе</p>
                  <p className="text-xs text-slate-400">Передайте заказчику API-ключ или JWT для входа в систему.</p>
                </div>
              </div>
              <div className="space-y-2 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4">
                <p className="flex items-center gap-1.5 text-sm text-amber-300">
                  <KeyRound className="h-4 w-4" /> Сохраните токены — JWT показывается один раз
                </p>
                {([["JWT", created.jwt_token], ["API-ключ", created.api_key]] as const).map(([label, val]) => (
                  <div key={label} className="flex items-center gap-2">
                    <span className="w-16 shrink-0 text-xs text-slate-400">{label}</span>
                    <code className="flex-1 truncate rounded bg-slate-950/60 px-2 py-1 text-xs text-slate-200">{val}</code>
                    <Button size="sm" variant="ghost" onClick={() => copy(val, label)}>
                      {copied === label ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" className="border-slate-700 text-slate-300" onClick={() => { reset(); }}>Создать ещё</Button>
                <Button className="bg-sky-500 text-white hover:bg-sky-600" onClick={() => { onCreated(); reset(); }}>Готово</Button>
              </div>
            </div>
          ) : (
            <>
              {/* stepper */}
              <div className="flex items-center justify-between gap-1 px-6 pt-5">
                {STEPS.map((st, i) => {
                  const Icon = st.icon;
                  const done = i < step, active = i === step;
                  return (
                    <React.Fragment key={i}>
                      <div className="flex flex-col items-center gap-1">
                        <div className={`flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${
                          active ? "border-sky-500 bg-sky-500/20 text-sky-300"
                          : done ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
                          : "border-slate-700 bg-slate-800/50 text-slate-500"}`}>
                          {done ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                        </div>
                        <span className={`text-[10px] ${active ? "text-sky-300" : "text-slate-500"}`}>{st.title}</span>
                      </div>
                      {i < STEPS.length - 1 && <div className={`mb-4 h-px flex-1 ${done ? "bg-emerald-500/40" : "bg-slate-700"}`} />}
                    </React.Fragment>
                  );
                })}
              </div>

              <div className="min-h-[280px] px-6 py-5">
                {error && (
                  <div className="mb-4 flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
                    <AlertTriangle className="h-4 w-4" /> {error}
                  </div>
                )}

                {step === 0 && (
                  <div className="space-y-4">
                    <Field label="Идентификатор (client_id)" hint="Латиницей, без пробелов — напр. pivzavod">
                      <input value={form.client_id} onChange={(e) => set("client_id", e.target.value.replace(/\s/g, ""))} className={inputCls} placeholder="pivzavod" />
                    </Field>
                    <Field label="Название заказчика">
                      <input value={form.name} onChange={(e) => set("name", e.target.value)} className={inputCls} placeholder="Пивзавод «Лидское»" />
                    </Field>
                  </div>
                )}

                {step === 1 && (
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <Field label="Host"><input value={form.ch_host} onChange={(e) => set("ch_host", e.target.value)} className={inputCls} /></Field>
                    <Field label="Port"><input type="number" value={form.ch_port} onChange={(e) => set("ch_port", e.target.value)} className={inputCls} /></Field>
                    <Field label="База данных" hint={`по умолчанию tenant_${form.client_id || "<id>"}`}>
                      <input value={form.ch_database} onChange={(e) => set("ch_database", e.target.value)} className={inputCls} placeholder={`tenant_${form.client_id || "id"}`} />
                    </Field>
                    <Field label="Пользователь"><input value={form.ch_user} onChange={(e) => set("ch_user", e.target.value)} className={inputCls} /></Field>
                    <Field label="Пароль" hint="шифруется at-rest (Fernet)">
                      <input type="password" value={form.ch_password} onChange={(e) => set("ch_password", e.target.value)} className={inputCls} />
                    </Field>
                  </div>
                )}

                {step === 2 && (
                  <div className="space-y-4">
                    <Field label="Разрешённые таблицы (через запятую)" hint="пусто = все таблицы базы">
                      <input value={form.allowed_tables} onChange={(e) => set("allowed_tables", e.target.value)} className={inputCls} placeholder="sales, orders, customers" />
                    </Field>
                    <Field label="Коллекция семантики (ChromaDB)" hint={`по умолчанию semantics_${form.client_id || "<id>"}`}>
                      <input value={form.vector_collection} onChange={(e) => set("vector_collection", e.target.value)} className={inputCls} placeholder={`semantics_${form.client_id || "id"}`} />
                    </Field>
                    <label className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/40 p-3 text-sm text-slate-300">
                      <input type="checkbox" checked={form.enforce_client_id} onChange={(e) => set("enforce_client_id", e.target.checked)} />
                      <ShieldCheck className="h-4 w-4 text-amber-400" />
                      Жёсткая row-isolation: добавлять <code className="text-xs">WHERE client_id = …</code> в каждый SQL
                    </label>
                  </div>
                )}

                {step === 3 && (
                  <div className="space-y-2 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4 text-sm">
                    <Row k="Идентификатор" v={form.client_id} />
                    <Row k="Название" v={form.name} />
                    <Row k="ClickHouse" v={`${form.ch_host}:${form.ch_port}/${form.ch_database || `tenant_${form.client_id}`}`} />
                    <Row k="Пользователь CH" v={form.ch_user} />
                    <Row k="Семантика" v={form.vector_collection || `semantics_${form.client_id}`} />
                    <Row k="Разрешённые таблицы" v={form.allowed_tables || "все"} />
                    <Row k="Row-isolation" v={form.enforce_client_id ? "включена" : "выключена"} />
                  </div>
                )}
              </div>

              {/* footer */}
              <div className="flex items-center justify-between border-t border-slate-700/50 px-6 py-4">
                <Button variant="ghost" className="text-slate-400" disabled={step === 0 || creating}
                  onClick={() => setStep((s) => Math.max(0, s - 1))}>
                  <ChevronLeft className="mr-1 h-4 w-4" /> Назад
                </Button>
                {step < STEPS.length - 1 ? (
                  <Button className="bg-sky-500 text-white hover:bg-sky-600" disabled={!canNext()}
                    onClick={() => setStep((s) => s + 1)}>
                    Далее <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                ) : (
                  <Button className="bg-emerald-500 text-white hover:bg-emerald-600" disabled={creating} onClick={submit}>
                    {creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
                    Создать блок
                  </Button>
                )}
              </div>
            </>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

const Field: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <label className="block space-y-1">
    <span className="text-xs text-slate-400">{label}</span>
    {children}
    {hint && <span className="block text-[11px] text-slate-600">{hint}</span>}
  </label>
);

const Row: React.FC<{ k: string; v: string }> = ({ k, v }) => (
  <div className="flex items-center justify-between gap-3 border-b border-slate-800/50 py-1.5 last:border-0">
    <span className="text-slate-500">{k}</span>
    <span className="truncate text-right font-medium text-slate-200">{v}</span>
  </div>
);
