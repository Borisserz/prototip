"""Тесты Orchestrator (Phase 5).

Моки всего пайплайна + 1-2 live end-to-end (реальные агенты + модель).
Проверяем, что PNG кладётся в out/, AskResult полностью заполнен.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.orchestrator import Orchestrator
from app.schemas import AnalysisResult, AskResult, ChartAgentResult
from core.llm import is_ollama_available
from core.models import ChartSpec


def test_orchestrator_mock_full_pipeline(tmp_path, monkeypatch):
    """Полный мок пайплайна: все агенты + рендер."""
    # Патчим out dir
    monkeypatch.setattr("app.orchestrator.Path", lambda x: tmp_path / x)  # грубо, но для теста

    orch = Orchestrator()

    # Моки - используем реальные модели, т.к. executor проверяет isinstance(..., SqlResult) и AgentResult
    from app.schemas import SqlResult

    mock_sql = SqlResult(
        sql="SELECT region, SUM(accrued) FROM df GROUP BY region LIMIT 5",
        data=[
            {"region": "г. Минск", "total": 1200000000},
            {"region": "Минская область", "total": 450000000},
        ],
        row_count=2,
        reasoning="mock data agent",
    )

    mock_analysis = AnalysisResult(
        insights=["Минск лидирует", "Рост в конце года", "Высокая собираемость по подоходному"],
        key_conclusion="г. Минск доминирует.",
        anomaly_or_trend="Аномалия в Гомеле",
    )

    mock_spec = ChartSpec(
        chart_type="bar",
        title="Начисления по регионам",
        x="region",
        y="total",
        agg="sum",
        rationale="Сравнение",
    )
    mock_chart = ChartAgentResult(spec=mock_spec)

    with (
        patch.object(orch.data_agent, "run", return_value=mock_sql),
        patch.object(orch.analyst_agent, "run", return_value=mock_analysis),
        patch.object(orch.chart_agent, "run", return_value=mock_chart),
        patch("app.orchestrator.build_chart") as mock_build,
        patch("app.orchestrator.export_png") as mock_export,
    ):
        mock_build.return_value = MagicMock()
        mock_export.return_value = tmp_path / "out" / "fake.png"

        res = orch.ask("Топ регионов по начислениям?")

    assert isinstance(res, AskResult)
    assert "SELECT" in res.sql
    assert res.analysis is not None
    assert len(res.analysis.insights) == 3
    assert res.chart_spec is not None
    assert res.png_path is not None


@pytest.mark.skipif(not is_ollama_available(), reason="Нужна модель для live Phase 5")
def test_orchestrator_live_end_to_end():
    """1-2 реальных end-to-end прогона. PNG должен появиться в out/."""
    orch = Orchestrator()

    questions = [
        "Какая динамика начислений по регионам?",
    ]

    for q in questions:
        res = orch.ask(q)

        assert isinstance(res, AskResult)
        assert res.sql.startswith("SELECT") or "ERROR" not in res.sql
        assert res.analysis is not None
        assert len(res.analysis.insights) >= 3
        assert res.chart_spec is not None
        assert res.png_path is not None
        assert "out/" in res.png_path or "chart_" in res.png_path

        # Проверить что файл реально создан
        from pathlib import Path

        assert Path(res.png_path).exists()
