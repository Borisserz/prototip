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
    """Регистрирует singleton PlannerAgent на shared executor (без дублирования)."""
    if "planner_agent" in executor.registry:
        return
    executor.register(get_planner())


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
    from app.agents.presentation_agent import PresentationAgent

    executor.register(DataAgent())
    executor.register(AnalystAgent())
    executor.register(ChartAgent())
    executor.register(DashboardAgent())
    executor.register(PresentationAgent())

    if include_planner:
        _register_planner_on_executor(executor)

    return executor


def get_planner(*, fresh: bool = False) -> Any:
    """Singleton PlannerAgent с общим LRU-кэшем (для Orchestrator и UI)."""
    global _planner

    from app.agents.planner_agent import PlannerAgent

    if fresh:
        return PlannerAgent(use_shared_executor=True)

    with _planner_lock:
        if _planner is None:
            _planner = PlannerAgent(use_shared_executor=True)
        return _planner