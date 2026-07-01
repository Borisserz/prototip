"""Тесты planner_utils: cache, trace."""

from __future__ import annotations

from app.agents.models import AgentCall, AgentResult, Plan
from app.planner_utils import PlannerResultCache, make_planner_trace, planner_cache_key
from app.schemas import DrilldownContext


def test_planner_cache_lru_eviction():
    cache = PlannerResultCache(max_size=2)
    r1 = AgentResult(success=True, reasoning="1")
    r2 = AgentResult(success=True, reasoning="2")
    r3 = AgentResult(success=True, reasoning="3")
    cache.set("a", r1)
    cache.set("b", r2)
    cache.get("a")
    cache.set("c", r3)
    assert cache.get("b") is None
    assert cache.get("a") is not None
    assert cache.get("c") is not None


def test_make_planner_trace():
    plan = Plan(goal="g", tasks=[], strategy="s")
    trace = make_planner_trace(
        plan,
        [{"num": 1, "agent_name": "data_agent", "description": "d", "status": "успешно"}],
        [AgentCall(agent_name="data_agent")],
    )
    assert trace.executed_plan == plan
    assert len(trace.plan_execution) == 1


def test_cache_key_stable():
    k1 = planner_cache_key("  Тест  ", None)
    k2 = planner_cache_key("тест", None)
    assert k1 == k2


def test_cache_key_drilldown_sensitive():
    dd = DrilldownContext(filters={"region": "Минск"})
    assert planner_cache_key("q", None) != planner_cache_key("q", dd)


def test_planner_cache_returns_deep_copy():
    cache = PlannerResultCache(max_size=4)
    original = AgentResult(success=True, reasoning="original")
    cache.set("k", original)
    copy = cache.get("k")
    assert copy is not None
    assert copy is not original
    copy.reasoning = "mutated"
    again = cache.get("k")
    assert again is not None
    assert again.reasoning == "original"
