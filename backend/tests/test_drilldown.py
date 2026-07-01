"""Unit tests for детализация helpers."""

from __future__ import annotations

from app.agents.data_agent import DataAgent
from app.agents.models import DataAgentInput, DrilldownContext
from app.drilldown import (
    build_detailed_analysis_question,
    build_drilldown_question,
    extract_drilldown_from_point,
)
from app.planner_utils import planner_cache_key as cache_key_fn
from core.models import ChartSpec


def test_extract_drilldown_horizontal_bar():
    spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Топ",
        x="debt",
        y="region",
        rationale="test",
    )
    point = {"y": "г. Минск", "x": 1000}
    filters = extract_drilldown_from_point(point, spec)
    assert filters.get("region") == "г. Минск"


def test_extract_drilldown_donut():
    spec = ChartSpec(
        chart_type="donut",
        title="Доли",
        x="tax_type",
        y="accrued",
        rationale="test",
    )
    point = {"label": "НДС"}
    filters = extract_drilldown_from_point(point, spec)
    assert filters.get("tax_type") == "НДС"


def test_build_drilldown_question_includes_trail():
    ctx = {"segment_label": "г. Минск", "dimension": "region", "filters": {"region": "г. Минск"}}
    trail = [{"dimension": "region", "label": "г. Минск", "value": "г. Минск"}]
    q = build_drilldown_question(ctx, trail)
    assert "г. Минск" in q
    assert "контекст детализации" in q


def test_build_detailed_analysis_question():
    q = build_detailed_analysis_question("2024-05-01")
    assert "2024-05-01" in q
    assert "структура и тренды" in q


def test_planner_cache_key_differs_by_drilldown():
    dd = DrilldownContext(filters={"region": "г. Минск"})
    k1 = cache_key_fn("Топ регионов", None)
    k2 = cache_key_fn("Топ регионов", dd)
    assert k1 != k2


def test_data_agent_drilldown_constraints_in_prompt():
    agent = DataAgent()
    prompt = agent._build_prompt(
        "Динамика по региону",
        drilldown_filters={"region": "г. Минск"},
    )
    assert "region = 'г. Минск'" in prompt
    assert "ОБЯЗАТЕЛЬНЫЕ фильтры" in prompt


def test_data_agent_input_accepts_drilldown():
    inp = DataAgentInput(
        question="Тестовый вопрос по данным", drilldown_filters={"region": "Брест"}
    )
    assert inp.drilldown_filters["region"] == "Брест"
