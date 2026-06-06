"""Тесты Orchestrator (Phase 5).

Моки PlannerAgent + live end-to-end (реальные агенты + модель).
Проверяем, что ask() проксирует AskResult от PlannerAgent (включая png_path).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.orchestrator import Orchestrator
from app.schemas import AnalysisResult, AskResult
from core.llm import is_ollama_available
from core.models import ChartSpec


def test_orchestrator_mock_full_pipeline(tmp_path):
    """Мок PlannerAgent.run → Orchestrator.ask() проксирует готовый AskResult с png_path."""
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
        data=[
            {"region": "г. Минск", "total": 1200000000},
            {"region": "Минская область", "total": 450000000},
        ],
        analysis=mock_analysis,
        chart_spec=mock_spec,
        png_path=str(png_file),
        reasoning="mock planner aggregate",
    )

    with patch("app.agents.planner_agent.PlannerAgent.run", return_value=fake_ask) as mock_run:
        res = orch.ask("Топ регионов по начислениям?")

    mock_run.assert_called_once_with("Топ регионов по начислениям?")
    assert res is fake_ask
    assert isinstance(res, AskResult)
    assert "SELECT" in res.sql
    assert res.analysis is not None
    assert len(res.analysis.insights) == 3
    assert res.chart_spec is not None
    assert res.chart_spec.chart_type == "bar"
    assert res.png_path == str(png_file)
    assert Path(res.png_path).exists()
    assert Path(res.png_path).stat().st_size > 0


@pytest.mark.skipif(not is_ollama_available(), reason="Нужна модель для live Phase 5")
def test_orchestrator_live_end_to_end():
    """Реальный end-to-end прогон. PNG должен появиться в out/."""
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
        assert Path(res.png_path).exists()
