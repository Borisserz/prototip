"""Тесты ChartAgent (Phase 4).

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

    with patch("app.agents.chart_agent.call_structured") as mock_call:
        mock_call.return_value = fake_spec
        result = agent.run(
            "Какие регионы лидируют по начислениям?", [{"region": "г. Минск", "accrued": 100}]
        )

    assert isinstance(result, ChartAgentResult)
    assert result.spec.chart_type == "bar"
    assert "регион" in result.spec.title.lower() or "начислено" in result.spec.title.lower()


@pytest.mark.live
@pytest.mark.skipif(not is_ollama_available(), reason="Ollama недоступен для живого Phase 4 теста")
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

        # Детерминированный рендер (главное Phase 1)
        df = pd.DataFrame(sql_res.data) if sql_res.data else pd.DataFrame()
        if not df.empty and spec.x in df.columns or spec.chart_type == "kpi":
            fig = build_chart(df, spec)
            assert fig is not None
            # Можно было бы export_png, но для теста достаточно
