"""Factory for a shared AgentExecutor.

The factory is the only place that wires concrete agents into AgentExecutor.
It uses local imports to avoid circular imports and a lock-protected singleton
so agents can safely call get_executor().run(...) from inside their run methods.
"""

from __future__ import annotations

import threading
from typing import Any

from app.agents.executor import AgentExecutor, AgentRegistry

_executor_lock = threading.RLock()
_executor: AgentExecutor | None = None
_executor_with_planner: bool = False
_planner_lock = threading.RLock()
_planner: Any = None


def _register_planner_on_executor(executor: AgentExecutor) -> None:
    pass


def get_executor(*, include_planner: bool = True, fresh: bool = False) -> AgentExecutor:
    """Return a configured AgentExecutor."""
    global _executor, _executor_with_planner

    if fresh:
        ex = _build_executor(include_planner=False)
        if include_planner:
            _register_planner_on_executor(ex)
        return ex

    with _executor_lock:
        if _executor is None:
            _executor = _build_executor(include_planner=False)
            _executor_with_planner = False
        if include_planner and not _executor_with_planner:
            _register_planner_on_executor(_executor)
            _executor_with_planner = True
        return _executor


def _build_executor(*, include_planner: bool) -> AgentExecutor:
    """Create and register standard leaf agents (planner — отдельно через get_planner)."""
    registry = AgentRegistry()
    executor = AgentExecutor(registry)

    from app.agents.analyst_agent import AnalystAgent
    from app.agents.chart_agent import ChartAgent
    from app.agents.dashboard_agent import DashboardAgent
    from app.agents.data_agent import DataAgent
    from app.agents.forecast_analyst_agent import ForecastAnalystAgent
    from app.agents.presentation_agent import PresentationAgent
    from app.agents.rag_agent import RagAgent
    from app.agents.report_docx_agent import ReportDocxAgent

    executor.register(DataAgent())
    executor.register(AnalystAgent())
    executor.register(ChartAgent())
    executor.register(DashboardAgent())
    executor.register(PresentationAgent())
    executor.register(RagAgent())
    executor.register(ReportDocxAgent())
    executor.register(ForecastAnalystAgent())

    if include_planner:
        _register_planner_on_executor(executor)

    return executor


def get_planner(*, fresh: bool = False) -> Any:
    return None
