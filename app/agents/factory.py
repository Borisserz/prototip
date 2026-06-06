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


def get_executor(*, include_planner: bool = True, fresh: bool = False) -> AgentExecutor:
    """Return a configured AgentExecutor.

    Args:
        include_planner: Register PlannerAgent too. Internal sub-agent calls usually
            do not need it, and setting this to False prevents recursive construction.
        fresh: Build a new isolated executor instead of using the shared singleton.

    The shared executor is protected by a re-entrant lock. Registration imports are
    intentionally local, because concrete agents may import this factory to call
    other agents as tools.
    """
    global _executor, _executor_with_planner

    if fresh:
        return _build_executor(include_planner=include_planner)

    with _executor_lock:
        if _executor is None:
            _executor = _build_executor(include_planner=include_planner)
            _executor_with_planner = include_planner
        elif include_planner and not _executor_with_planner:
            from app.agents.planner_agent import PlannerAgent

            if "planner_agent" not in _executor.registry:
                _executor.register(PlannerAgent(use_shared_executor=False))
            _executor_with_planner = True
        return _executor


def _build_executor(*, include_planner: bool) -> AgentExecutor:
    """Create and register all standard agents."""
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
        from app.agents.planner_agent import PlannerAgent

        executor.register(PlannerAgent(use_shared_executor=False))

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
