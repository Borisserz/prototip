"""Thread-safe live pipeline state for Streamlit AI Pipeline Visualizer.

Агенты и Planner пишут этапы сюда; UI опрашивает snapshot() в отдельном потоке.
Вложенные вызовы (presentation → planner) подавляют emit через suppress_pipeline_emit().
"""

from __future__ import annotations

import copy
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

PIPELINE_STAGES: list[dict[str, str]] = [
    {"id": "intent", "label": "Анализ намерения", "icon": "🧠"},
    {"id": "sql", "label": "Генерация SQL", "icon": "🗄️"},
    {"id": "duckdb", "label": "Обработка данных (DuckDB)", "icon": "🔍"},
    {"id": "synthesis", "label": "Текстовый синтез", "icon": "📝"},
    {"id": "viz", "label": "Визуализация", "icon": "🎨"},
]

AGENT_START_STAGE: dict[str, str] = {
    "data_agent": "sql",
    "analyst_agent": "synthesis",
    "chart_agent": "viz",
    "dashboard_agent": "viz",
    "presentation_agent": "synthesis",
    "planner_agent": "intent",
}

AGENT_DONE_STAGE: dict[str, str] = {
    "data_agent": "duckdb",
    "analyst_agent": "synthesis",
    "chart_agent": "viz",
    "dashboard_agent": "viz",
    "presentation_agent": "synthesis",
    "planner_agent": "intent",
}

_pipeline_suppress_depth: ContextVar[int] = ContextVar("pipeline_suppress_depth", default=0)

PIPELINE_WORKER_TIMEOUT_SEC = 600


def pipeline_emit_enabled() -> bool:
    """False внутри suppress_pipeline_emit (вложенные planner/presentation)."""
    return _pipeline_suppress_depth.get() == 0


@contextmanager
def suppress_pipeline_emit():
    """Подавляет emit этапов для вложенных вызовов агентов."""
    token = _pipeline_suppress_depth.set(_pipeline_suppress_depth.get() + 1)
    try:
        yield
    finally:
        _pipeline_suppress_depth.reset(token)


class PipelineStore:
    """Глобальное хранилище прогресса пайплайна (потокобезопасное)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}

    def reset(self, run_id: str, question: str = "") -> None:
        with self._lock:
            stages = {
                s["id"]: {"status": "pending", "log": "", "error": None, "agent": ""}
                for s in PIPELINE_STAGES
            }
            stages["intent"]["status"] = "running"
            stages["intent"]["log"] = "Инициализация конвейера агентов..."
            self._data = {
                "run_id": run_id,
                "question": question,
                "active_stages": ["intent"],
                "stages": stages,
                "events": [],
                "finished": False,
                "fatal_error": None,
                "started_at": time.time(),
            }

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._data) and not self._data.get("finished", True)

    def set_stage(
        self,
        stage_id: str,
        status: str,
        log: str = "",
        *,
        agent: str = "",
        error: str | None = None,
    ) -> None:
        with self._lock:
            if not self._data or stage_id not in self._data.get("stages", {}):
                return
            st = self._data["stages"][stage_id]
            st["status"] = status
            if log:
                st["log"] = log
            if agent:
                st["agent"] = agent
            if error:
                st["error"] = error
            elif status in ("running", "done"):
                st["error"] = None

            active = set(self._data.get("active_stages", []))
            if status == "running":
                active.add(stage_id)
                self._data["active_stages"] = sorted(active, key=_stage_order_key)
            elif status in ("done", "error"):
                active.discard(stage_id)

            self._data["active_stages"] = sorted(active, key=_stage_order_key)
            self._data["events"].append(
                {
                    "ts": time.time(),
                    "stage": stage_id,
                    "status": status,
                    "log": log,
                    "agent": agent,
                    "error": error,
                }
            )
            if len(self._data["events"]) > 40:
                self._data["events"] = self._data["events"][-40:]

    def finish(self, *, success: bool = True, error: str | None = None) -> None:
        with self._lock:
            if not self._data:
                return
            self._data["finished"] = True
            if error:
                self._data["fatal_error"] = error
            for sid, st in self._data.get("stages", {}).items():
                if st["status"] == "running":
                    st["status"] = "done" if success else "error"
                    if not success and error and not st.get("error"):
                        st["error"] = error
            self._data["active_stages"] = []
            self._data["events"].append(
                {
                    "ts": time.time(),
                    "stage": "pipeline",
                    "status": "done" if success else "error",
                    "log": "Конвейер завершён" if success else (error or "Ошибка"),
                    "agent": "",
                    "error": error,
                }
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data) if self._data else {}


def _stage_order_key(stage_id: str) -> int:
    order = [s["id"] for s in PIPELINE_STAGES]
    return order.index(stage_id) if stage_id in order else 99


pipeline_store = PipelineStore()


def emit_pipeline_stage(
    stage_id: str,
    status: str,
    log: str = "",
    *,
    agent: str = "",
    error: str | None = None,
) -> None:
    """Удобный хелпер для агентов."""
    if not pipeline_emit_enabled():
        return
    pipeline_store.set_stage(stage_id, status, log, agent=agent, error=error)


def emit_agent_started(agent_name: str, detail: str = "") -> None:
    if not pipeline_emit_enabled():
        return
    stage = AGENT_START_STAGE.get(agent_name)
    if stage:
        emit_pipeline_stage(
            stage,
            "running",
            detail or f"{agent_name}: выполнение...",
            agent=agent_name,
        )


def emit_agent_finished(
    agent_name: str, success: bool, brief: str = "", error: str | None = None
) -> None:
    if not pipeline_emit_enabled():
        return
    stage = AGENT_DONE_STAGE.get(agent_name, AGENT_START_STAGE.get(agent_name))
    if not stage:
        return
    status = "done" if success else "error"
    emit_pipeline_stage(
        stage, status, brief or ("Готово" if success else "Ошибка"), agent=agent_name, error=error
    )


def emit_cache_hit_progress() -> None:
    """Синтетический прогресс при cache hit PlannerAgent."""
    if not pipeline_emit_enabled():
        return
    emit_pipeline_stage("intent", "done", "План из кэша — повторный запрос", agent="planner_agent")