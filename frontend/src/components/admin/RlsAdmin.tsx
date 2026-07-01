import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft, RefreshCw, ShieldCheck, Loader2, AlertTriangle, Check, MapPin, Save, LayoutGrid, Activity,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { rlsApi, type RlsRules } from "@/lib/adminApi";
import { ConsoleTabs } from "./widgets";

interface Props {
  onBack: () => void;
  onTabChange: (id: string) => void;
}

/**
 * RLS-консоль «Доступ по ролям».
 * Админ задаёт, какие регионы видит каждая роль (например, grodno_manager → Гродненская область).
 * Сохраняется в ClickHouse (default.rls_role_filters) и применяется агентами на лету
 * как WHERE region IN (...). Заменяет жёстко зашитый маппинг роль→регион.
 */
export const RlsAdmin: React.FC<Props> = ({ onBack, onTabChange }) => {
  const [data, setData] = useState<RlsRules | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // локальный черновик выбранных значений по ролям
  const [draft, setDraft] = useState<Record<string, Set<string>>>({});
  const [savingRole, setSavingRole] = useState<string | null>(null);
  const [savedRole, setSavedRole] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await rlsApi.get();
      setData(d);
      const next: Record<string, Set<string>> = {};
      for (const role of d.roles) {
        next[role] = new Set(d.rules[role]?.[d.column] || []);
      }
      setDraft(next);
    } catch (e: any) {
      setError(e?.message || "Не удалось загрузить правила доступа");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const column = data?.column || "region";
  const regions = data?.regions || [];

  const toggle = (role: string, region: string) => {
    setDraft((prev) => {
      const set = new Set(prev[role] || []);
      if (set.has(region)) set.delete(region);
      else set.add(region);
      return { ...prev, [role]: set };
    });
    setSavedRole(null);
  };

  const dirty = (role: string): boolean => {
    const orig = new Set(data?.rules[role]?.[column] || []);
    const cur = draft[role] || new Set<string>();
    if (orig.size !== cur.size) return true;
    for (const v of cur) if (!orig.has(v)) return true;
    return false;
  };

  const save = async (role: string) => {
    setSavingRole(role);
    setError(null);
    try {
      const values = Array.from(draft[role] || []);
      await rlsApi.setRule(role, values, column);
      setData((prev) =>
        prev
          ? { ...prev, rules: { ...prev.rules, [role]: { ...(prev.rules[role] || {}), [column]: values } } }
          : prev,
      );
      setSavedRole(role);
      setTimeout(() => setSavedRole((r) => (r === role ? null : r)), 2500);
    } catch (e: any) {
      setError(e?.message || "Не удалось сохранить");
    } finally {
      setSavingRole(null);
    }
  };

  const roles = useMemo(() => data?.roles || [], [data]);

  return (
    <div className="h-full overflow-y-auto custom-scrollbar bg-slate-900/30 px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-5xl">
        {/* Заголовок */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={onBack} className="text-slate-400 hover:text-white">
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
                <ShieldCheck className="h-6 w-6 text-emerald-400" /> Доступ по ролям
              </h1>
              <p className="text-sm text-slate-400">
                Какие регионы видит каждая роль. Применяется к данным как фильтр <code>{column} IN (...)</code>.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ConsoleTabs
              current="access"
              onChange={onTabChange}
              tabs={[
                { id: "blocks", label: "Мои блоки", icon: LayoutGrid },
                { id: "monitoring", label: "Мониторинг", icon: Activity },
                { id: "access", label: "Доступ", icon: ShieldCheck },
              ]}
            />
            <Button variant="ghost" onClick={load} className="text-slate-300" title="Обновить">
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
            <AlertTriangle className="h-4 w-4" /> {error}
          </div>
        )}

        {loading && !data ? (
          <div className="flex items-center gap-2 py-12 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" /> Загрузка…
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            {roles.length === 0 && (
              <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-6 text-sm text-slate-400">
                Роли не найдены. Создайте пользователей с ролями (например, <code>grodno_manager</code>).
              </div>
            )}

            {roles.map((role) => {
              const selected = draft[role] || new Set<string>();
              const isUnrestricted = selected.size === 0;
              return (
                <motion.div
                  key={role}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-5"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-slate-700/60 px-2 py-1 font-mono text-sm text-sky-300">{role}</span>
                      {isUnrestricted ? (
                        <span className="text-xs text-amber-300/80">видит все регионы (нет ограничений)</span>
                      ) : (
                        <span className="text-xs text-slate-400">
                          {selected.size} регион(ов) выбрано
                        </span>
                      )}
                    </div>
                    <Button
                      onClick={() => save(role)}
                      disabled={!dirty(role) || savingRole === role}
                      className="bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40"
                      size="sm"
                    >
                      {savingRole === role ? (
                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                      ) : savedRole === role ? (
                        <Check className="mr-1 h-4 w-4" />
                      ) : (
                        <Save className="mr-1 h-4 w-4" />
                      )}
                      {savedRole === role ? "Сохранено" : "Сохранить"}
                    </Button>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {regions.map((region) => {
                      const on = selected.has(region);
                      return (
                        <button
                          key={region}
                          onClick={() => toggle(role, region)}
                          className={[
                            "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                            on
                              ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                              : "border-slate-600/60 bg-slate-700/30 text-slate-300 hover:border-slate-500 hover:text-white",
                          ].join(" ")}
                        >
                          {on ? <Check className="h-3.5 w-3.5" /> : <MapPin className="h-3.5 w-3.5 opacity-60" />}
                          {region}
                        </button>
                      );
                    })}
                    {regions.length === 0 && (
                      <span className="text-xs text-slate-500">
                        Нет значений региона в DWH (таблица enterprise_taxes пуста?).
                      </span>
                    )}
                  </div>
                </motion.div>
              );
            })}

            <p className="pt-2 text-xs text-slate-500">
              Пустой выбор = роль видит все данные. Изменения применяются к новым запросам почти сразу (кэш ~30с).
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
