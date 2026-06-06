"""Unit-тесты pure helpers UI (без Streamlit runtime)."""

from __future__ import annotations

from app.agents.models import AgentCall, Plan, PlanExecutionStep, PlannerTrace
from app.schemas import AskResult
from core.models import ChartSpec
from ui.components.pipeline import pipeline_status_headline, pipeline_step_markdown
from ui.components.trace import result_has_trace
from ui.streamlit_app import (
    DASHBOARD_CHART_TYPES,
    _chart_display_title,
    _drilldown_supported,
    _filter_data_by_regions,
    _normalize_result,
)


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


def test_chart_display_title_prefers_action_title():
    spec = ChartSpec(
        chart_type="bar",
        title="Описание",
        x="region",
        y="accrued",
        action_title="г. Минск лидирует",
        rationale="t",
    )
    assert _chart_display_title(spec, "fallback") == "г. Минск лидирует"


def test_drilldown_supported_matrix():
    treemap = ChartSpec(
        chart_type="treemap",
        title="t",
        x="region",
        y="accrued",
        rationale="t",
    )
    assert _drilldown_supported(treemap) is True
    bar = ChartSpec(chart_type="bar", title="t", x="region", y="accrued", rationale="t")
    assert _drilldown_supported(bar) is True
    kpi = ChartSpec(chart_type="kpi", title="t", x="x", y="accrued", rationale="t")
    assert _drilldown_supported(kpi) is False


def test_filter_data_by_regions():
    data = [
        {"region": "г. Минск", "accrued": 1},
        {"region": "Гомельская область", "accrued": 2},
    ]
    filtered = _filter_data_by_regions(data, ["г. Минск"])
    assert len(filtered) == 1
    assert filtered[0]["region"] == "г. Минск"


def test_dashboard_chart_types_complete():
    assert "treemap" in DASHBOARD_CHART_TYPES
    assert "waterfall" in DASHBOARD_CHART_TYPES