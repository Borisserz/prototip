"""Unit-тесты pure helpers UI (без Streamlit runtime)."""

from __future__ import annotations

from app.agents.models import AgentCall, Plan, PlanExecutionStep, PlannerTrace
from app.schemas import AskResult
from ui.components.pipeline import pipeline_step_markdown, pipeline_status_headline
from ui.components.trace import result_has_trace
from ui.streamlit_app import _normalize_result


def test_pipeline_step_markdown_empty():
    text = pipeline_step_markdown({})
    assert "Инициализация" in text


def test_pipeline_status_headline_finished():
    snap = {
        "finished": True,
        "stages": {"intent": {"status": "done", "log": "ok"}},
        "active_stages": [],
    }
    label = pipeline_status_headline(snap)
    assert "заверш" in label.lower() or "Конвейер" in label


def test_result_has_trace():
    plan = Plan(goal="g", tasks=[], strategy="s")
    trace = PlannerTrace(
        executed_plan=plan,
        plan_execution=[PlanExecutionStep(num=1, agent_name="data_agent", description="d", status="успешно")],
        agent_calls=[AgentCall(agent_name="data_agent")],
    )
    res = AskResult(question="q", sql="", data=[], reasoning="r", trace=trace)
    assert result_has_trace(res) is True
    assert result_has_trace(AskResult(question="q", sql="", data=[], reasoning="r")) is False


def test_result_has_trace_on_failed_ask():
    plan = Plan(goal="g", tasks=[], strategy="s")
    trace = PlannerTrace(
        executed_plan=plan,
        plan_execution=[
            PlanExecutionStep(num=1, agent_name="data_agent", description="d", status="ошибка")
        ],
        agent_calls=[],
    )
    res = AskResult(
        question="q",
        sql="",
        data=[],
        reasoning="fail",
        success=False,
        error="boom",
        trace=trace,
    )
    assert result_has_trace(res) is True


def test_normalize_result_dict_ask():
    raw = {
        "question": "q",
        "sql": "SELECT 1",
        "data": [],
        "reasoning": "r",
        "success": True,
    }
    res = _normalize_result(raw)
    assert isinstance(res, AskResult)