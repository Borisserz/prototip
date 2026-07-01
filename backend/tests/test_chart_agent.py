"""Тесты ChartAgent.

Мок LLM → ChartSpec. Живой прогон + связка DataAgent -> ChartAgent -> build_chart (визуальный рендер).
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from app.agents.chart_agent import ChartAgent
from app.agents.data_agent import DataAgent
from app.schemas import ChartAgentResult
from core.llm import is_ollama_available
from core.models import ChartSpec
from viz.charts import build_chart


def test_chart_agent_mock_returns_spec() -> None:
    """Мок: модель возвращает валидный ChartSpec."""
    agent = ChartAgent()

    fake_spec = ChartSpec(
        chart_type="bar",
        title="Начислено по регионам",
        x="region",
        y="accrued",
        agg="sum",
        rationale="Сравнение категорий — bar",
    )

    # ChartAgent ожидает ChartList (обёртка с полем charts: list[ChartSpec])
    fake_list = type("ChartList", (), {"charts": [fake_spec]})()
    with patch("app.agents.chart_agent.call_structured") as mock_call:
        mock_call.return_value = fake_list
        result = agent.run(
            "Какие регионы лидируют по начислениям?", [{"region": "г. Минск", "accrued": 100}]
        )

    assert isinstance(result, ChartAgentResult)
    assert len(result.specs) >= 1
    assert result.specs[0].chart_type == "bar"
    assert "регион" in result.specs[0].title.lower() or "начислено" in result.specs[0].title.lower()


def test_chart_agent_storytelling_spec_fields() -> None:
    """ChartSpec с Data Storytelling полями проходит через ChartAgent."""
    agent = ChartAgent()
    fake_spec = ChartSpec(
        chart_type="treemap",
        title="Структура начислений",
        x="region",
        color="tax_type",
        y="accrued",
        action_title="г. Минск доминирует",
        show_average=False,
        highlight_category=None,
        rationale="иерархия → treemap",
    )
    fake_list = type("ChartList", (), {"charts": [fake_spec]})()
    with patch("app.agents.chart_agent.call_structured") as mock_call:
        mock_call.return_value = fake_list
        result = agent.run(
            "Структура по регионам и налогам",
            [{"region": "г. Минск", "tax_type": "НДС", "accrued": 1}],
        )

    assert result.specs[0].chart_type == "treemap"
    assert result.specs[0].action_title == "г. Минск доминирует"


@pytest.mark.live
@pytest.mark.skipif(not is_ollama_available(), reason="Ollama недоступен для живого теста")
def test_chart_agent_live_and_e2e_with_dataagent() -> None:
    """Живой ChartAgent + end-to-end с DataAgent + build_chart на 2-3 вопросах."""
    data_agent = DataAgent()
    chart_agent = ChartAgent()

    questions = [
        "Динамика начислений по регионам за год",
        "Структура (доли) налогов по видам в г. Минск",
    ]

    for q in questions:
        sql_res = data_agent.run(q)
        assert sql_res.row_count >= 0

        # Передаём данные (records) в ChartAgent
        chart_res = chart_agent.run(q, sql_res.data)
        spec = chart_res.spec
        assert isinstance(spec, ChartSpec)
        assert spec.chart_type in {
            "line",
            "bar",
            "grouped_bar",
            "stacked_bar",
            "donut",
            "horizontal_bar",
            "kpi",
            "heatmap",
        }

        # Детерминированный рендер
        df = pd.DataFrame(sql_res.data) if sql_res.data else pd.DataFrame()
        if not df.empty and spec.x in df.columns or spec.chart_type == "kpi":
            fig = build_chart(df, spec)
            assert fig is not None
            # Можно было бы export_png, но для теста достаточно
