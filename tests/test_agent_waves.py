"""Тесты улучшений волн 1–3: честный success, slide pipeline, degraded fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agent_context import presentation_subplan
from app.agents.analyst_agent import AnalystAgent
from app.agents.chart_agent import ChartAgent
from app.agents.factory import get_planner
from app.agents.models import (
    AnalysisResult,
    AskResult,
    ChartAgentResult,
    Plan,
    SqlResult,
    Task,
)
from app.agents.planner_agent import PlannerAgent
from app.slide_pipeline import build_slide_ask_result
from core.models import ChartSpec


def test_get_planner_uses_shared_executor_singleton():
    p1 = get_planner()
    p2 = get_planner()
    assert p1 is p2
    assert p1.executor is get_planner().executor


def test_aggregate_result_fails_when_data_empty():
    planner = PlannerAgent(use_shared_executor=False)
    plan = Plan(
        goal="q",
        tasks=[
            Task(id="d", description="d", agent_name="data_agent", params={"question": "q"}),
            Task(
                id="c",
                description="c",
                agent_name="chart_agent",
                params={"question": "q"},
                depends_on=["d"],
            ),
        ],
    )
    data_res = SqlResult(sql="SELECT 1", data=[], row_count=0, success=False, error="empty")
    chart_spec = ChartSpec(chart_type="bar", title="t", x="r", y="a", rationale="r")
    chart_res = ChartAgentResult(spec=chart_spec, reasoning="ok")
    context = {"d": data_res, "c": chart_res}
    result = planner._aggregate_result(plan, context, "q")
    assert isinstance(result, AskResult)
    assert result.success is False


def test_skip_dependent_tasks_when_parent_fails():
    planner = PlannerAgent(use_shared_executor=False)
    plan = Plan(
        goal="q",
        tasks=[
            Task(id="d", description="d", agent_name="data_agent", params={"question": "q"}),
            Task(
                id="c",
                description="c",
                agent_name="chart_agent",
                params={"question": "q"},
                depends_on=["d"],
            ),
        ],
    )
    data_res = SqlResult(sql="bad", data=[], row_count=0, success=False, error="sql fail")

    def run_side_effect(agent_name: str, *args, **kwargs):
        if agent_name == "data_agent":
            return data_res
        raise AssertionError(f"chart_agent should be skipped, got call: {agent_name}")

    planner.executor.run = MagicMock(side_effect=run_side_effect)  # type: ignore[method-assign]
    result = planner._execute_plan(plan, "q")
    assert isinstance(result, AskResult)
    assert result.success is False
    assert result.trace is not None
    skipped = [s for s in result.trace.plan_execution if s.agent_name == "chart_agent"]
    assert skipped and skipped[0].status == "ошибка"


def test_analyst_llm_fallback_is_degraded_not_success():
    agent = AnalystAgent()
    with patch("app.agents.analyst_agent.call_structured", side_effect=RuntimeError("down")):
        res = agent.run("вопрос", [{"region": "г. Минск", "debt": 1}])
    assert res.success is False
    assert res.degraded is True


def test_slide_pipeline_builds_ask_result_without_planner():
    sql_res = SqlResult(
        sql="SELECT region, SUM(debt) AS total FROM df GROUP BY region",
        data=[{"region": "г. Минск", "total": 100}],
        row_count=1,
    )
    chart_spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Топ",
        x="region",
        y="total",
        rationale="рейтинг",
    )
    chart_res = ChartAgentResult(spec=chart_spec, reasoning="ok")
    analysis = AnalysisResult(
        insights=["i1", "i2", "i3"],
        key_conclusion="вывод",
        reasoning="ok",
    )

    def run_side_effect(agent_name: str, *args, **kwargs):
        if agent_name == "data_agent":
            return sql_res
        if agent_name == "chart_agent":
            return chart_res
        if agent_name == "analyst_agent":
            return analysis
        raise AssertionError(agent_name)

    executor = MagicMock()
    executor.run.side_effect = run_side_effect
    result = build_slide_ask_result("задолженность по регионам", executor)
    assert isinstance(result, AskResult)
    assert result.success is True
    assert result.chart_spec is not None
    assert "planner_agent" not in [c[0] for c in executor.run.call_args_list]


def test_forbidden_agents_in_subplan_context():
    planner = PlannerAgent(use_shared_executor=False)
    with presentation_subplan():
        errors = planner._validate_plan(
            Plan(
                goal="nested",
                tasks=[
                    Task(
                        id="p1",
                        description="pres",
                        agent_name="presentation_agent",
                        params={"questions": ["q"]},
                    )
                ],
            )
        )
    assert any("запрещён во вложенном контексте" in e for e in errors)


def test_chart_agent_retries_on_llm_error():
    agent = ChartAgent()
    good = ChartSpec(chart_type="bar", title="t", x="region", y="debt", rationale="r")
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return good

    with patch("app.agents.chart_agent.call_structured", side_effect=flaky):
        res = agent.run("топ регионов", [{"region": "г. Минск", "debt": 1}])
    assert res.spec.chart_type == "bar"
    assert calls["n"] == 2