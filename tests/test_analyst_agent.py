"""Тесты AnalystAgent (Phase 3).

Моки + live на 3 вопросах (используя реальную модель qwen2.5-coder:7b-instruct).
Анализ данных из DataAgent (Беларусь).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agents.analyst_agent import AnalystAgent
from app.agents.data_agent import DataAgent
from app.schemas import AnalysisResult
from core.llm import is_ollama_available


def test_analyst_agent_mock() -> None:
    """Мок LLM: возвращает валидный AnalysisResult."""
    agent = AnalystAgent()

    fake_result = AnalysisResult(
        insights=[
            "г. Минск обеспечивает львиную долю поступлений.",
            "Наблюдается рост начислений в конце года.",
            "Задолженность по имущественным налогам выше в восточных областях.",
        ],
        key_conclusion="г. Минск — ключевой регион, требуется работа с собираемостью в регионах.",
        anomaly_or_trend="Сезонный всплеск в 4 квартале.",
    )

    sample_data = [{"region": "г. Минск", "accrued": 500000000, "tax_type": "НДС"}]

    with patch("app.agents.analyst_agent.call_structured") as mock_call:
        mock_call.return_value = fake_result
        result = agent.run("Какая динамика по регионам?", sample_data)

    assert isinstance(result, AnalysisResult)
    assert len(result.insights) >= 3
    assert "Минск" in result.key_conclusion or "регион" in result.key_conclusion.lower()


def test_analyst_agent_includes_chart_spec_in_prompt() -> None:
    """При переданном chart_spec промпт содержит контекст визуализации."""
    agent = AnalystAgent()
    sample_data = [{"region": "г. Минск", "debt": 100}]
    chart_spec = {
        "chart_type": "horizontal_bar",
        "title": "Топ регионов по задолженности",
        "x": "region",
        "y": "debt",
        "rationale": "рейтинг",
    }

    fake_result = AnalysisResult(
        insights=[
            "Как видно на горизонтальной диаграмме, г. Минск лидирует.",
            "Задолженность сконцентрирована в нескольких областях.",
            "Собираемость по подоходному налогу высокая.",
        ],
        key_conclusion="Горизонтальная диаграмма подтверждает доминирование г. Минска.",
        anomaly_or_trend=None,
    )

    with patch("app.agents.analyst_agent.call_structured") as mock_call:
        mock_call.return_value = fake_result
        result = agent.run("Задолженность по регионам", sample_data, chart_spec=chart_spec)

    assert isinstance(result, AnalysisResult)
    prompt_arg = mock_call.call_args[0][0]
    assert "Топ регионов по задолженности" in prompt_arg
    assert "horizontal_bar" in prompt_arg or "горизонтальной" in prompt_arg


@pytest.mark.skipif(
    not is_ollama_available(), reason="Ollama + модель недоступна для live теста Phase 3"
)
def test_analyst_agent_live_3_questions() -> None:
    """Live: AnalystAgent на реальных данных DataAgent (3 вопроса)."""
    data_agent = DataAgent()
    analyst = AnalystAgent()

    questions = [
        "Динамика начислений по регионам за год",
        "Где самая большая задолженность?",
        "Структура налогов по видам в г. Минск",
    ]

    for q in questions:
        sql_res = data_agent.run(q)
        assert sql_res.row_count >= 0

        analysis = analyst.run_from_sql(q, sql_res)  # or analyst.run(q, sql_res.data)
        assert isinstance(analysis, AnalysisResult)
        assert len(analysis.insights) >= 3
        assert len(analysis.key_conclusion) > 10
        # Все тексты должны быть на русском (простая проверка)
        assert any(
            ord(c) > 127 for c in " ".join(analysis.insights) + analysis.key_conclusion
        )  # кириллица
