"""Тесты DashboardAgent (next sprint).

Мок LLM (call_structured) → DashboardResult.
Проверка переиспользования ChartSpec, graceful degradation, вызовов под-агентов (моки),
валидация структуры (KPI + charts + layout + insights + reasoning).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.dashboard_agent import DashboardAgent
from app.schemas import DashboardLayout, DashboardRequest, DashboardResult, KpiCard
from core.llm import is_ollama_available
from core.models import ChartSpec


def test_dashboard_agent_mock_returns_full_result() -> None:
    """Мок: LLM возвращает валидный DashboardResult с вложенными ChartSpec."""
    agent = DashboardAgent()

    fake_composition = MagicMock()
    fake_composition.title = "Дашборд задолженности по регионам РБ"
    fake_composition.summary = "Задолженность сконцентрирована в нескольких областях. г. Минск показывает лучшую собираемость."
    fake_composition.kpi_cards = [
        KpiCard(name="Общая задолженность", value=15.2, unit="млрд Br"),
        KpiCard(name="Топ-регион", value="Гомельская область", unit=""),
    ]
    fake_composition.charts = [
        ChartSpec(
            chart_type="horizontal_bar",
            title="Топ регионов по задолженности",
            x="region",
            y="total_debt",
            agg="sum",
            rationale="Рейтинг регионов — лучший читаемый тип для топа",
        ),
        ChartSpec(
            chart_type="donut",
            title="Структура задолженности по видам налогов",
            x="tax_type",
            y="debt",
            agg="sum",
            rationale="Доли по налогам — donut",
        ),
    ]
    fake_composition.layout = DashboardLayout(type="kpi_top_grid", columns=2)
    fake_composition.insights = [
        "Гомельская область лидирует по абсолютной задолженности",
        "По Подоходному налогу собираемость высокая",
    ]
    fake_composition.reasoning = "Выбрали horizontal_bar + donut как классическую пару для ранжирования и структуры. Layout grid для KPI сверху."

    with patch("app.agents.dashboard_agent.call_structured") as mock_call:
        mock_call.return_value = fake_composition
        # Также мокаем DataAgent и Analyst, чтобы не зависеть от реальных данных/LLM
        with (
            patch("app.agents.dashboard_agent._get_data_agent") as mock_data,
            patch("app.agents.dashboard_agent._get_analyst_agent") as mock_analyst,
        ):
            mock_data_inst = MagicMock()
            mock_data_inst.run.return_value.data = [
                {"region": "Гомельская область", "debt": 5000000000, "accrued": 30000000000},
                {"region": "г. Минск", "debt": 800000000, "accrued": 45000000000},
            ]
            mock_data_inst.run.return_value.sql = "SELECT region, SUM(debt) as total_debt FROM df GROUP BY region ORDER BY total_debt DESC LIMIT 10"
            mock_data.return_value = mock_data_inst

            mock_anal = MagicMock()
            mock_anal.run.return_value.insights = ["Дополнительный инсайт из Analyst"]
            mock_analyst.return_value = mock_anal

            req = DashboardRequest(
                question="Покажи дашборд по задолженности по регионам",
                max_charts=3,
                include_kpi=True,
            )
            result = agent.run(req)

    assert isinstance(result, DashboardResult)
    assert "Дашборд" in result.title or "задолженности" in result.title.lower()
    assert len(result.charts) >= 1
    assert all(isinstance(c, ChartSpec) for c in result.charts)
    assert result.layout.type in {"kpi_top_grid", "two_column", "tabs", "single_column"}
    assert len(result.insights) >= 1
    assert result.reasoning
    # KPI могут быть от LLM или от _compute_basic_kpis
    assert isinstance(result.kpi_cards, list)
    # Новые поля для рендера/отладки (data + source_sql)
    assert isinstance(result.data, list)
    assert result.source_sql is not None and "SELECT" in (result.source_sql or "").upper()


def test_dashboard_agent_graceful_no_data() -> None:
    """Graceful degradation: нет данных → валидный минимальный результат без падения."""
    agent = DashboardAgent()

    with patch("app.agents.dashboard_agent._get_data_agent") as mock_data:
        mock_data_inst = MagicMock()
        mock_data_inst.run.return_value.data = []
        mock_data_inst.run.return_value.sql = ""
        mock_data.return_value = mock_data_inst

        req = DashboardRequest(question="Дашборд по несуществующему фильтру")
        result = agent.run(req)

    assert isinstance(result, DashboardResult)
    assert result.charts == []
    assert len(result.insights) >= 1
    assert (
        "данн" in result.summary.lower()
        or "отсутств" in result.summary.lower()
        or "не удалось" in result.summary.lower()
    )


@pytest.mark.skipif(
    not is_ollama_available(), reason="Ollama недоступен для живого теста DashboardAgent"
)
def test_dashboard_agent_live_minimal() -> None:
    """Живой (опциональный) прогон на реальном вопросе — проверяем, что агент не падает и возвращает разумную структуру."""
    agent = DashboardAgent()
    req = DashboardRequest(
        question="Ключевые метрики и дашборд по начислениям в г. Минск",
        max_charts=3,
        include_kpi=True,
    )
    result = agent.run(req)

    assert isinstance(result, DashboardResult)
    assert result.title
    assert len(result.charts) <= 3
    assert result.reasoning
    # На реальных данных должны быть хотя бы KPI или графики
    assert result.kpi_cards or result.charts
