import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Play, RefreshCw, CalendarClock, Loader2, CheckCircle2, XCircle, Clock,
  Database, FileText, Upload, Sparkles, AlertTriangle, PlugZap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { etlApi, type EtlRun, type EtlStatus, type TenantConfig, type TenantDoc } from "@/lib/adminApi";

interface Props {
  clientId: string;
  client: TenantConfig;
  onChanged?: () => void;
}

const CRON_PRESETS = [
  { label: "Ежедневно в 03:00", value: "0 3 * * *" },
  { label: "Каждые 6 часов", value: "0 */6 * * *" },
  { label: "Каждый час", value: "0 * * * *" },
  { label: "Еженедельно (Пн 02:00)", value: "0 2 * * 1" },
  { label: "Каждые 30 минут", value: "*/30 * * * *" },
];

const inputCls =
  "w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-200 focus:border-sky-500/50 focus:outline-none";

const STATUS_META: Record<string, { icon: any; cls: string; label: string }> = {
  success:  { icon: CheckCircle2, cls: "text-emerald-400", label: "Успешно" },
  running:  { icon: Loader2,      cls: "text-sky-400 animate-spin", label: "Выполняется" },
  queued:   { icon: Clock,        cls: "text-amber-400", label: "В очереди" },
  failed:   { icon: XCircle,      cls: "text-rose-400", label: "Ошибка" },
  idle:     { icon: Clock,        cls: "text-slate-500", label: "Не запускался" },
};

/** операционная панель ETL клиента (Airflow / inline). */
export const EtlPanel: React.FC<Props> = ({ clientId, client, onChanged }) => {
  const [status, setStatus] = useState<EtlStatus | null>(null);
  const [runs, setRuns] = useState<EtlRun[]>([]);
  const [docs, setDocs] = useState<TenantDoc[]>([]);
  const [runsSource, setRunsSource] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const [pgDsn, setPgDsn] = useState("");
  const [pgSchema, setPgSchema] = useState(client.pg_schema || "public");
  const [schedule, setSchedule] = useState(client.etl_schedule || "0 3 * * *");
  const [enabled, setEnabled] = useState(!!client.etl_enabled);

  const fileRef = useRef<HTMLInputElement>(null);

  const flash = (kind: "ok" | "err", text: string) => {
    setMsg({ kind, text });
    setTimeout(() => setMsg(null), 5000);
  };

  const refresh = useCallback(async () => {
    try {
      const [s, r, d] = await Promise.all([
        etlApi.status(clientId),
        etlApi.runs(clientId, 8),
        etlApi.listDocs(clientId),
      ]);
      setStatus(s);
      setRuns(r.runs || []);
      setRunsSource(r.source);
      setDocs(d.documents || []);
      setSchedule(s.etl_schedule || schedule);
      setEnabled(!!s.etl_enabled);
    } catch (e: any) {
      flash("err", e?.message || "Не удалось загрузить статус ETL");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  useEffect(() => { refresh(); }, [refresh]);

  // авто-обновление, пока ETL выполняется
  useEffect(() => {
    if (status?.status !== "running") return;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [status?.status, refresh]);

  const saveConnection = async () => {
    if (!pgDsn.trim()) { flash("err", "Введите DSN Postgres"); return; }
    setBusy("provision");
    try {
      const probe = await etlApi.probeConnection(pgDsn.trim(), pgSchema || "public");
      const r = await etlApi.provision(clientId, { pg_dsn: pgDsn.trim(), pg_schema: pgSchema || "public" });
      flash("ok", `Подключено (${probe.count} табл.) — инициализация запущена (${r.mode === "Airflow" ? "Airflow" : "inline"})`);
      setPgDsn("");
      onChanged?.();
      refresh();
    } catch (e: any) {
      flash("err", e?.message || "Не удалось подключить БД");
    } finally {
      setBusy(null);
    }
  };

  const runSync = async () => {
    setBusy("run");
    try {
      const r = await etlApi.run(clientId, {});
      flash("ok", `Синхронизация запущена (${r.mode === "Airflow" ? "Airflow" : "inline"})`);
      refresh();
    } catch (e: any) {
      flash("err", e?.message || "Не удалось запустить ETL");
    } finally {
      setBusy(null);
    }
  };

  const rebuildSemantics = async () => {
    setBusy("semantics");
    try {
      await etlApi.rebuildSemantics(clientId);
      flash("ok", "Пересборка семантического слоя запущена");
      refresh();
    } catch (e: any) {
      flash("err", e?.message || "Не удалось пересобрать семантику");
    } finally {
      setBusy(null);
    }
  };

  const saveSchedule = async () => {
    setBusy("schedule");
    try {
      const r = await etlApi.setSchedule(clientId, { etl_schedule: schedule, etl_enabled: enabled });
      flash("ok", r.note || "Расписание сохранено");
      onChanged?.();
      refresh();
    } catch (e: any) {
      flash("err", e?.message || "Не удалось сохранить расписание");
    } finally {
      setBusy(null);
    }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setBusy("docs");
    try {
      for (const f of files) await etlApi.uploadDoc(clientId, f);
      flash("ok", `Загружено документов: ${files.length} — индексируются в RAG`);
      setTimeout(refresh, 1500);
    } catch (err: any) {
      flash("err", err?.message || "Не удалось загрузить документ");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const st = STATUS_META[status?.status || "idle"] || STATUS_META.idle;
  const StIcon = st.icon;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6 space-y-6">
      {msg && (
        <div className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${
          msg.kind === "ok"
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
            : "border-rose-500/30 bg-rose-500/10 text-rose-300"}`}>
          {msg.kind === "ok" ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />} {msg.text}
        </div>
      )}

      {/* Статус + действия */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <StIcon className={`h-6 w-6 ${st.cls}`} />
            <div>
              <p className="text-sm font-medium text-slate-200">Статус ETL: <span className={st.cls}>{st.label}</span></p>
              <p className="text-xs text-slate-500">
                {status?.last_run_at ? `Последний запуск: ${new Date(status.last_run_at).toLocaleString("ru-RU")}` : "Запусков ещё не было"}
                {status?.message ? ` · ${status.message}` : ""}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={refresh} className="text-slate-300" title="Обновить">
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button onClick={rebuildSemantics} disabled={!status?.pg_configured || !!busy}
              variant="outline" className="border-slate-700 text-slate-200">
              {busy === "semantics" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4 text-violet-400" />}
              Пересобрать семантику
            </Button>
            <Button onClick={runSync} disabled={!status?.pg_configured || !!busy}
              className="bg-emerald-500 text-white hover:bg-emerald-600">
              {busy === "run" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              Запустить синхронизацию
            </Button>
          </div>
        </div>
        {!status?.pg_configured && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
            <PlugZap className="h-4 w-4" /> Postgres-источник не подключён — подключите БД ниже, чтобы запустить инициализацию инстанса.
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Подключение БД / инициализация */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
            <Database className="h-4 w-4 text-sky-400" /> Подключение Postgres (инициализация)
          </h3>
          <div className="space-y-3">
            <input value={pgDsn} onChange={(e) => setPgDsn(e.target.value)} className={inputCls}
              placeholder="postgresql://ro_user:pwd@db.client:5432/erp" />
            <div className="flex gap-2">
              <input value={pgSchema} onChange={(e) => setPgSchema(e.target.value)} className={inputCls} placeholder="public" />
              <Button onClick={saveConnection} disabled={!!busy || !pgDsn.trim()} className="bg-sky-500 text-white hover:bg-sky-600 whitespace-nowrap">
                {busy === "provision" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlugZap className="mr-2 h-4 w-4" />}
                Подключить и инициализировать
              </Button>
            </div>
            <p className="text-[11px] text-slate-600">
              Снимет слепок read-only БД заказчика в ClickHouse и сгенерирует семантику. DSN шифруется at-rest.
            </p>
          </div>
        </div>

        {/* Расписание */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
            <CalendarClock className="h-4 w-4 text-sky-400" /> Расписание автосинхронизации
          </h3>
          <div className="space-y-3">
            <select value={CRON_PRESETS.some((p) => p.value === schedule) ? schedule : "custom"}
              onChange={(e) => { if (e.target.value !== "custom") setSchedule(e.target.value); }} className={inputCls}>
              {CRON_PRESETS.map((p) => <option key={p.value} value={p.value}>{p.label} ({p.value})</option>)}
              <option value="custom">Своё расписание…</option>
            </select>
            <input value={schedule} onChange={(e) => setSchedule(e.target.value)} className={inputCls} placeholder="0 3 * * *" />
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              Включить автосинхронизацию по расписанию (Airflow)
            </label>
            <Button onClick={saveSchedule} disabled={!!busy} variant="outline" className="w-full border-slate-700 text-slate-200">
              {busy === "schedule" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CalendarClock className="mr-2 h-4 w-4" />}
              Сохранить расписание
            </Button>
          </div>
        </div>
      </div>

      {/* Документация в RAG */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-medium text-slate-200">
            <FileText className="h-4 w-4 text-emerald-400" /> Документация клиента (RAG)
          </h3>
          <div>
            <input ref={fileRef} type="file" multiple accept=".pdf,.txt,.md,.docx" className="hidden" onChange={onUpload} />
            <Button onClick={() => fileRef.current?.click()} disabled={!!busy}
              className="bg-emerald-500 text-white hover:bg-emerald-600">
              {busy === "docs" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
              Загрузить документ
            </Button>
          </div>
        </div>
        {docs.length ? (
          <div className="table-wrapper overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500">
                  <th className="pb-2">Документ</th>
                  <th className="pb-2 text-right">Чанков</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.source} className="border-t border-slate-800/50">
                    <td className="py-2 text-slate-300">{d.source}</td>
                    <td className="py-2 text-right text-slate-400">{d.chunks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-slate-500">
            Документов пока нет. Загрузите PDF/DOCX/TXT/MD — они проиндексируются в персональный RAG клиента (по аналогии с базой знаний по НК, но в его предметной области).
          </p>
        )}
      </div>

      {/* История запусков */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
          <Clock className="h-4 w-4 text-slate-400" /> История запусков
          <span className="text-[11px] text-slate-600">({runsSource === "Airflow" ? "Airflow" : "реестр"})</span>
        </h3>
        {runs.length ? (
          <div className="space-y-2">
            {runs.map((r, i) => {
              const m = STATUS_META[r.state] || STATUS_META.idle;
              const Icon = m.icon;
              return (
                <div key={r.dag_run_id + i} className="flex items-center justify-between rounded-lg border border-slate-800/50 bg-slate-950/30 px-3 py-2 text-xs">
                  <span className="flex items-center gap-2">
                    <Icon className={`h-4 w-4 ${m.cls}`} />
                    <span className="text-slate-300">{m.label}</span>
                  </span>
                  <span className="text-slate-500">{r.execution_date ? new Date(r.execution_date).toLocaleString("ru-RU") : r.dag_run_id}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-xs text-slate-500">Запусков ещё не было.</p>
        )}
      </div>
    </motion.div>
  );
};
