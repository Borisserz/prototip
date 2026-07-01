"""Тесты DashboardAgent (next sprint).

Мок LLM (call_structured) → DashboardResult.
Проверка переиспользования ChartSpec, безопасное игнорирование ошибок, вызовов под-агентов (моки),
валидация структуры (KPI + charts + layout + insights + reasoning).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.dashboard_agent import DashboardAgent
from app.schemas import (
    AnalysisResult,
    ChartAgentResult,
    DashboardLayout,
    DashboardRequest,
    DashboardResult,
    KpiCard,
    SqlResult,
)
from core.llm import is_ollama_available
from core.models import ChartSpec


def _mock_executor(
    *, data_rows: list[dict], sql: str = "", analyst_insights: list[str] | None = None
):
    """Возвращает мок AgentExecutor для DashboardAgent (tool-calling через get_executor)."""
    mock_ex = MagicMock()

    def run_side_effect(agent_name: str, *args, **kwargs):
        if agent_name == "data_agent":
            return SqlResult(
                step_by_step_planning="mock plan",
                sql=sql,
                data=data_rows,
                row_count=len(data_rows),
                reasoning="mock data",
            )
        if agent_name == "analyst_agent":
            return AnalysisResult(
                insights=analyst_insights or ["Дополнительный инсайт из Analyst"],
                key_conclusion="ok",
                reasoning="mock analyst",
            )
        if agent_name == "chart_agent":
            idea = args[0] if args else "chart"
            return ChartAgentResult(
                specs=[
                    ChartSpec(
                        chart_type="horizontal_bar",
                        title=str(idea)[:60],
                        x="region",
                        y="total_debt",
                        agg="sum",
                        rationale="mock chart",
                    )
                ],
                reasoning="mock chart",
            )
        return MagicMock(success=False, error=f"unknown agent {agent_name}")

    mock_ex.run.side_effect = run_side_effect
    return mock_ex


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
    fake_composition.chart_ideas = [
        "Топ регионов по задолженности",
        "Структура по видам налогов",
    ]
    fake_composition.layout = DashboardLayout(type="kpi_top_grid", columns=2)
    fake_composition.insights = [
        "Гомельская область лидирует по абсолютной задолженности",
        "По Подоходному налогу собираемость высокая",
    ]
    fake_composition.reasoning = "Выбрали horizontal_bar + donut как классическую пару для ранжирования и структуры. Layout grid для KPI сверху."

    sample_data = [
        {"region": "Гомельская область", "debt": 5000000000, "accrued": 30000000000},
        {"region": "г. Минск", "debt": 800000000, "accrued": 45000000000},
    ]
    sample_sql = "SELECT region, SUM(debt) as total_debt FROM df GROUP BY region ORDER BY total_debt DESC LIMIT 10"

    with patch("app.agents.dashboard_agent.call_structured") as mock_call:
        mock_call.return_value = fake_composition
        with patch(
            "app.agents.dashboard_agent.get_executor",
            return_value=_mock_executor(data_rows=sample_data, sql=sample_sql),
        ):
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
    assert isinstance(result.kpi_cards, list)
    assert isinstance(result.data, list)
    assert result.source_sql is not None and "SELECT" in (result.source_sql or "").upper()


def test_dashboard_agent_graceful_no_data() -> None:
    """безопасное игнорирование ошибок: нет данных → валидный минимальный результат без падения."""
    agent = DashboardAgent()

    with patch(
        "app.agents.dashboard_agent.get_executor",
        return_value=_mock_executor(data_rows=[], sql=""),
    ):
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


@pytest.mark.live
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
    assert result.kpi_cards or result.charts
