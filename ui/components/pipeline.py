"""Нативный Live Execution Log для st.status."""

from __future__ import annotations

from typing import Any

from app.pipeline_progress import PIPELINE_STAGES

_PIPELINE_STEP_DONE_RU: dict[str, str] = {
    "intent": "Анализ намерения выполнен",
    "sql": "Генерация SQL-запроса выполнена",
    "duckdb": "Обработка данных завершена",
    "synthesis": "Текстовый синтез выполнен",
    "viz": "Визуализация построена",
}


def pipeline_stage_label(stage_id: str, stage_state: dict[str, Any]) -> str:
    meta = next((s for s in PIPELINE_STAGES if s["id"] == stage_id), None)
    if meta is None:
        return stage_id
    if stage_id == "synthesis" and stage_state.get("agent") == "analyst_agent":
        return "Анализ инсайтов"
    return meta["label"]


def pipeline_stage_icon(stage_id: str) -> str:
    meta = next((s for s in PIPELINE_STAGES if s["id"] == stage_id), None)
    return meta["icon"] if meta else "▪️"


def pipeline_effective_status(stage_id: str, stage_state: dict[str, Any], *, finished: bool) -> str:
    status = stage_state.get("status") or "pending"
    if finished and status == "pending":
        return "skipped"
    return status


def pipeline_status_headline(snapshot: dict[str, Any]) -> str:
    if not snapshot:
        return "AI-конвейер запускается..."
    if snapshot.get("fatal_error"):
        return "Ошибка в конвейере агентов"
    active = snapshot.get("active_stages") or []
    if active:
        sid = active[-1]
        stg = snapshot.get("stages", {}).get(sid, {})
        icon = pipeline_stage_icon(sid)
        label = pipeline_stage_label(sid, stg)
        return f"{icon} {label}…"
    if snapshot.get("finished"):
        stages = snapshot.get("stages", {})
        if any(s.get("status") == "error" for s in stages.values()):
            return "Конвейер завершён с ошибками"
        return "Конвейер завершён"
    return "Агенты работают над вашим запросом..."


def pipeline_step_markdown(snapshot: dict[str, Any]) -> str:
    if not snapshot:
        return "Инициализация конвейера…"

    finished = bool(snapshot.get("finished"))
    stages_data = snapshot.get("stages") or {}
    lines: list[str] = []

    for meta in PIPELINE_STAGES:
        sid = meta["id"]
        stg = stages_data.get(sid, {})
        eff = pipeline_effective_status(sid, stg, finished=finished)
        label = pipeline_stage_label(sid, stg)
        log_text = (stg.get("log") or "").strip()

        if eff == "done":
            done_text = _PIPELINE_STEP_DONE_RU.get(sid, f"{label} выполнен")
            lines.append(f"✅ {done_text}")
        elif eff == "running":
            detail = log_text or label
            lines.append(f"● {detail}…")
        elif eff == "error":
            err = stg.get("error") or log_text or "ошибка"
            lines.append(f"❌ {label}: {err}")
        elif eff == "skipped":
            lines.append(f"— {label}: не требуется")
        else:
            lines.append(f"○ {label}")

    return "\n\n".join(lines)


def update_pipeline_live_ui(live_slot: Any, status: Any, snapshot: dict[str, Any]) -> None:
    live_slot.markdown(pipeline_step_markdown(snapshot))
    try:
        status.update(label=pipeline_status_headline(snapshot))
    except Exception:
        pass