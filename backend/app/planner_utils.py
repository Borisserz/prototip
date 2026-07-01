"""Утилиты PlannerAgent: trace, кэш-ключи."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from app.agents.models import (
    AgentCall,
    AgentResult,
    DrilldownContext,
    Plan,
    PlanExecutionStep,
    PlannerTrace,
)
from app.config import config


def _dataset_mtime_token() -> str:
    path = Path(config.data_path)
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return "0"


def make_planner_trace(
    plan: Plan,
    plan_execution: list[dict[str, Any]],
    agent_calls: list[AgentCall],
) -> PlannerTrace:
    steps = [
        PlanExecutionStep(
            num=int(step["num"]),
            agent_name=str(step["agent_name"]),
            description=str(step["description"]),
            status=str(step["status"]),
            brief_result=str(step.get("brief_result") or ""),
            depends_on=list(step.get("depends_on") or []),
        )
        for step in plan_execution
    ]
    return PlannerTrace(executed_plan=plan, plan_execution=steps, agent_calls=agent_calls)


def attach_planner_trace(result: AgentResult, trace: PlannerTrace) -> AgentResult:
    result.trace = trace
    return result


def planner_cache_key(question: str, drilldown: DrilldownContext | None) -> str:
    payload = {
        "q": question.strip().lower()[:200],
        "dd": drilldown.filters if drilldown else {},
        "trail": drilldown.trail if drilldown else [],
        "ds_mtime": _dataset_mtime_token(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class PlannerResultCache:
    """LRU-кэш результатов PlannerAgent."""

    def __init__(self, max_size: int | None = None) -> None:
        self._max_size = max_size or config.planner_cache_size
        self._store: OrderedDict[str, AgentResult] = OrderedDict()

    def get(self, key: str) -> AgentResult | None:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        cached = self._store[key]
        if hasattr(cached, "model_copy"):
            return cached.model_copy(deep=True)
        return cached

    def set(self, key: str, value: AgentResult) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)
