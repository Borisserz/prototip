"""Тесты фабрики AgentExecutor и параллельного выполнения PlannerAgent."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from app.agents.factory import get_executor
from app.agents.models import AskResult, ChartAgentResult, Plan, SqlResult, Task
from app.agents.planner_agent import PlannerAgent
from core.models import ChartSpec


def test_get_executor_registers_all_agents():
    """Фабрика создаёт executor с полным набором агентов."""
    executor = get_executor(include_planner=True, fresh=True)
    names = set(executor.list_agents())
    assert {
        "data_agent",
        "analyst_agent",
        "chart_agent",
        "dashboard_agent",
        "presentation_agent",
        "planner_agent",
    }.issubset(names)


def test_get_executor_singleton_is_thread_safe():
    """Повторные вызовы get_executor() возвращают один и тот же экземпляр."""
    ex1 = get_executor(include_planner=False)
    ex2 = get_executor(include_planner=False)
    assert ex1 is ex2


def test_planner_parallel_v_graph_aggregates_ask_result():
    """V-граф data → [analyst, chart] выполняется и агрегируется в AskResult."""
    planner = PlannerAgent(use_shared_executor=False)

    sql_res = SqlResult(
        sql="SELECT region, SUM(accrued) AS total FROM df GROUP BY region",
        data=[{"region": "г. Минск", "total": 100}],
        row_count=1,
        reasoning="data ok",
    )
    chart_spec = ChartSpec(
        chart_type="bar",
        title="Топ",
        x="region",
        y="total",
        agg="sum",
        rationale="bar for compare",
    )
    chart_res = ChartAgentResult(spec=chart_spec, reasoning="chart ok")

    parallel_started: list[tuple[str, float]] = []
    parallel_lock = threading.Lock()

    def run_side_effect(agent_name: str, *args, **kwargs):
        if agent_name == "data_agent":
            time.sleep(0.05)
            return sql_res
        if agent_name in ("analyst_agent", "chart_agent"):
            with parallel_lock:
                parallel_started.append((agent_name, time.time()))
            time.sleep(0.12)
            if agent_name == "chart_agent":
                return chart_res
            from app.agents.models import AnalysisResult

            return AnalysisResult(
                insights=["i1", "i2", "i3"],
                key_conclusion="ok",
                reasoning="analyst ok",
            )
        return MagicMock(success=False, error=agent_name)

    planner.executor.run = MagicMock(side_effect=run_side_effect)  # type: ignore[method-assign]

    plan = Plan(
        goal="Покажи данные, график и выводы",
        tasks=[
            Task(
                id="t1",
                description="Получить данные",
                agent_name="data_agent",
                params={"question": "сводка"},
                depends_on=[],
            ),
            Task(
                id="t2",
                description="Анализ",
                agent_name="analyst_agent",
                params={"question": "сводка"},
                depends_on=["t1"],
            ),
            Task(
                id="t3",
                description="График",
                agent_name="chart_agent",
                params={"question": "топ регионов"},
                depends_on=["t1"],
            ),
        ],
        strategy="V-graph parallel",
    )

    with (
        patch("app.agents.planner_agent.build_chart") as mock_build,
        patch("app.agents.planner_agent.export_png") as mock_export,
    ):
        mock_build.return_value = MagicMock()
        mock_export.return_value = None
        result = planner._execute_plan(plan, "Покажи данные, график и выводы")

    assert isinstance(result, AskResult)
    assert result.sql == sql_res.sql
    assert result.data == sql_res.data
    assert result.analysis is not None
    assert result.chart_spec is not None
    assert len(result.analysis.insights) >= 3  # type: ignore[union-attr]

    analyst_starts = [ts for name, ts in parallel_started if name == "analyst_agent"]
    chart_starts = [ts for name, ts in parallel_started if name == "chart_agent"]
    assert analyst_starts and chart_starts
    assert abs(analyst_starts[0] - chart_starts[0]) < 0.08


def test_planner_diamond_injects_chart_spec_into_analyst():
    """Diamond data → chart → analyst: chart_spec прокидывается в analyst_agent."""
    planner = PlannerAgent(use_shared_executor=False)

    sql_res = SqlResult(
        sql="SELECT region, SUM(debt) AS total_debt FROM df GROUP BY region",
        data=[{"region": "г. Минск", "total_debt": 100}],
        row_count=1,
        reasoning="data ok",
    )
    chart_spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Топ регионов по задолженности",
        x="region",
        y="total_debt",
        agg="sum",
        rationale="рейтинг",
    )
    chart_res = ChartAgentResult(spec=chart_spec, reasoning="chart ok")

    captured_kwargs: list[dict] = []

    def run_side_effect(agent_name: str, *args, **kwargs):
        if agent_name == "data_agent":
            return sql_res
        if agent_name == "chart_agent":
            return chart_res
        if agent_name == "analyst_agent":
            captured_kwargs.append(dict(kwargs))
            from app.agents.models import AnalysisResult

            return AnalysisResult(
                insights=[
                    "Как видно на горизонтальной диаграмме, лидирует г. Минск",
                    "i2",
                    "i3",
                ],
                key_conclusion="Диаграмма подтверждает концентрацию долга.",
                reasoning="analyst with chart",
            )
        return MagicMock(success=False, error=agent_name)

    planner.executor.run = MagicMock(side_effect=run_side_effect)  # type: ignore[method-assign]

    plan = Plan(
        goal="Данные, график и выводы",
        tasks=[
            Task(
                id="t1",
                description="Данные",
                agent_name="data_agent",
                params={"question": "задолженность region debt"},
                depends_on=[],
            ),
            Task(
                id="t2",
                description="График",
                agent_name="chart_agent",
                params={"question": "топ регионов"},
                depends_on=["t1"],
            ),
            Task(
                id="t3",
                description="Анализ",
                agent_name="analyst_agent",
                params={"question": "выводы"},
                depends_on=["t1", "t2"],
            ),
        ],
        strategy="Diamond",
    )

    with (
        patch("app.agents.planner_agent.build_chart") as mock_build,
        patch("app.agents.planner_agent.export_png"),
    ):
        mock_build.return_value = MagicMock()
        result = planner._execute_plan(plan, "Данные, график и выводы")

    assert isinstance(result, AskResult)
    assert captured_kwargs
    assert captured_kwargs[0].get("chart_spec") is not None
    assert captured_kwargs[0]["chart_spec"]["chart_type"] == "horizontal_bar"
    assert captured_kwargs[0]["chart_spec"]["title"] == "Топ регионов по задолженности"
