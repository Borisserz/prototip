"""Тесты Orchestrator (unified facade)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.models import AgentCall, Plan, PlanExecutionStep, PlannerTrace, Task
from app.orchestrator import Orchestrator
from app.schemas import AnalysisResult, AskResult, DashboardResult, DrilldownContext
from core.llm import is_ollama_available
from core.models import ChartSpec


def _sample_trace() -> PlannerTrace:
    plan = Plan(
        goal="Тест",
        tasks=[Task(id="t1", description="data", agent_name="data_agent", params={})],
        strategy="test",
    )
    return PlannerTrace(
        executed_plan=plan,
        plan_execution=[
            PlanExecutionStep(
                num=1,
                agent_name="data_agent",
                description="Получить данные",
                status="успешно",
                brief_result="5 строк",
            )
        ],
        agent_calls=[AgentCall(agent_name="data_agent", success=True, output_summary="ok")],
    )


def test_orchestrator_uses_planner_singleton():
    from app.agents.factory import get_planner

    orch = Orchestrator()
    # Orchestrator теперь исполняет через LangGraph + executor (planner-singleton живёт в factory)
    assert orch.executor is not None
    assert get_planner() is get_planner()


def test_orchestrator_mock_ask_returns_result_with_trace(tmp_path):
    orch = Orchestrator()

    mock_analysis = AnalysisResult(
        insights=["Минск лидирует", "Рост в конце года", "Высокая собираемость по подоходному"],
        key_conclusion="г. Минск доминирует.",
        anomaly_or_trend="Аномалия в Гомеле",
        reasoning="mock analyst",
    )
    mock_spec = ChartSpec(
        chart_type="bar",
        title="Начисления по регионам",
        x="region",
        y="total",
        agg="sum",
        rationale="Сравнение",
    )
    png_file = tmp_path / "out" / "fake.png"
    png_file.parent.mkdir(parents=True, exist_ok=True)
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    fake_ask = AskResult(
        question="Топ регионов по начислениям?",
        sql="SELECT region, SUM(accrued) FROM df GROUP BY region LIMIT 5",
        data=[{"region": "г. Минск", "total": 1200000000}],
        analysis=mock_analysis,
        chart_spec=mock_spec,
        png_path=str(png_file),
        reasoning="mock planner aggregate",
        trace=_sample_trace(),
    )

    # ask() исполняется через LangGraph: патчим graph.invoke -> final_state с final_result
    with patch("app.graph.graph.invoke", return_value={"final_result": fake_ask}) as mock_run:
        res = orch.ask("Топ регионов по начислениям?")

    mock_run.assert_called_once()
    assert res is fake_ask
    assert res.trace is not None
    assert res.trace.executed_plan is not None


def test_orchestrator_dashboard_via_executor():
    orch = Orchestrator()
    fake_dash = DashboardResult(
        title="Дашборд",
        summary="Сводка",
        reasoning="mock",
    )
    with patch.object(orch.executor, "run", return_value=fake_dash) as mock_run:
        res = orch.dashboard("Дашборд по регионам", max_charts=3)

    mock_run.assert_called_once()
    assert res.title == "Дашборд"


def test_orchestrator_presentation_via_executor():
    orch = Orchestrator()
    fake_pres = MagicMock()
    fake_pres.num_slides = 5
    fake_pres.success = True
    with patch.object(orch.executor, "run", return_value=fake_pres) as mock_run:
        res = orch.presentation(["Вопрос 1"], num_slides=5)

    mock_run.assert_called_once()
    assert res.num_slides == 5


def test_orchestrator_ask_drilldown_passthrough():
    orch = Orchestrator()
    dd = DrilldownContext(filters={"region": "г. Минск"})
    fake = AskResult(question="q", sql="SELECT 1", data=[], reasoning="ok")

    captured: dict = {}

    def fake_invoke(state, config=None):
        captured["state"] = state
        return {"final_result": fake}

    with patch("app.graph.graph.invoke", side_effect=fake_invoke):
        orch.ask("Динамика", drilldown=dd)

    # drilldown должен прокидываться в начальный стейт графа
    assert captured["state"]["drilldown"] is dd
    assert captured["state"]["question"] == "Динамика"


def test_orchestrator_ask_result_fallback():
    orch = Orchestrator()
    dash = DashboardResult(title="T", summary="S", reasoning="r", data=[{"a": 1}])
    dash.trace = _sample_trace()
    fb = orch.ask_result_fallback("Вопрос", dash)
    assert isinstance(fb, AskResult)
    assert fb.question == "Вопрос"
    assert fb.trace is not None


@pytest.mark.live
@pytest.mark.skipif(not is_ollama_available(), reason="Нужна модель для live теста")
def test_orchestrator_live_end_to_end():
    orch = Orchestrator()
    res = orch.ask("Какая динамика начислений по регионам?")
    assert isinstance(res, AskResult)
    assert res.analysis is not None or res.chart_spec is not None or res.data
