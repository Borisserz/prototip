"""E2E тесты Phase 8: полный прогон без моков через Orchestrator.

Покрывает реальный вызов Data+Analyst+Chart+render.
Гейт: для вопроса про структуру (доли) -> png, >=3 insights, sql.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.orchestrator import Orchestrator
from core.llm import is_ollama_available


@pytest.mark.live
@pytest.mark.skipif(
    not is_ollama_available(),
    reason="Нужна модель Ollama qwen2.5-coder:7b-instruct для e2e Phase 8",
)
def test_e2e_orchestrator_structure_by_tax_types_full_pipeline():
    """Полный реальный прогон Orchestrator.ask без моков.

    Вопрос 'Структура налогов по видам (доли)' -> donut-like, png >0 байт,
    analysis.insights >=3, sql не пустой.
    """
    orch = Orchestrator()
    question = "Структура налогов по видам (доли)"
    res = orch.ask(question)

    # sql не пустой и валидный SELECT
    assert res.sql, "sql должен быть непустым"
    assert "SELECT" in res.sql.upper(), f"sql должен быть SELECT, got: {res.sql[:80]}"

    # данные пришли
    assert res.data, "должны быть данные из SQL"

    # анализ: >=3 insights (по схеме min 3)
    assert res.analysis is not None
    assert len(res.analysis.insights) >= 3
    assert res.analysis.key_conclusion  # не пустой

    # png_path существует и файл >0 байт
    assert res.png_path is not None
    png = Path(res.png_path)
    assert png.exists(), f"png не создан: {res.png_path}"
    size = png.stat().st_size
    assert size > 0, f"png пустой (0 байт): {res.png_path}, size={size}"

    # chart_spec заполнен
    assert res.chart_spec is not None
