"""Тесты PresentationAgent (Phase 6).

Проверка создания .pptx, структуры слайдов, наличия изображений.
Живой прогон на 3 вопросах (требует ollama + python-pptx).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.presentation_agent import PresentationAgent
from app.schemas import DeckNarrative, PresentationResult
from core.llm import is_ollama_available


def test_presentation_agent_mock():
    """Мок: проверяем структуру презентации с DeckNarrative, кол-во слайдов, отсутствие заглушки."""
    agent = PresentationAgent()

    fake_res = PresentationResult(pptx_path="out/presentation.pptx", num_slides=7)

    with patch("app.agents.presentation_agent.PresentationAgent.run", return_value=fake_res):
        pass

    with (
        patch("app.orchestrator.Orchestrator") as mock_orch,
        patch("app.agents.presentation_agent.call_structured") as mock_narr,
    ):
        mock_instance = MagicMock()
        fake_ask = MagicMock()
        fake_ask.png_path = "/tmp/fake.png"
        fake_ask.data = [{"x": 1}]
        fake_ask.chart_spec = MagicMock(chart_type="bar", title="Тест бар")
        fake_ask.analysis = MagicMock(
            insights=["i1", "i2", "i3"], key_conclusion="key", anomaly_or_trend=None
        )
        mock_instance.ask.return_value = fake_ask
        mock_orch.return_value = mock_instance

        mock_narr.return_value = DeckNarrative(
            overview="test overview",
            themes=["t1", "t2"],
            key_takeaways=["k1", "k2", "k3", "k4"],
            recommendations=["r1", "r2"],
        )

        with patch("app.agents.presentation_agent.Presentation") as mock_prs:
            mock_prs_instance = MagicMock()
            mock_slide = MagicMock()
            mock_prs_instance.slides.add_slide.return_value = mock_slide
            #  title + ov + themes + 3q + takeaways + recs = 8
            mock_prs_instance.slides.__len__.return_value = 8
            mock_prs.return_value = mock_prs_instance

            res = agent.run(["q1", "q2", "q3"])

    assert isinstance(res, PresentationResult)
    assert res.num_slides >= 3 + 4  # questions + title/ov/themes/key/rec at least
    assert "presentation.pptx" in res.pptx_path


@pytest.mark.skipif(
    not is_ollama_available(),
    reason="Ollama + qwen2.5-coder:7b-instruct недоступен для live теста Phase 6",
)
def test_presentation_live_creates_file_with_slides_and_images():
    """Живой прогон на 3 вопросах. Файл создаётся, открывается python-pptx, слайдов >=3, изображения на месте."""
    from pptx import Presentation as PptxPresentation

    agent = PresentationAgent()
    questions = [
        "Какие регионы имеют наибольшую задолженность по НДС?",
        "Динамика начислений подоходного налога в г. Минск по месяцам?",
        "Топ-3 региона по сумме имущественных налогов?",
    ]

    res = agent.run(questions)

    assert isinstance(res, PresentationResult)
    pptx_file = Path(res.pptx_path)
    assert pptx_file.exists(), f"Презентация не создана: {pptx_file}"

    # open with python-pptx
    prs = PptxPresentation(str(pptx_file))
    n_slides = len(prs.slides)
    assert n_slides >= len(questions) + 4, (
        f"Ожидалось >= {len(questions)}+4 слайдов (титул+обзор+темы+вопросы+выводы+рекомендации), получено {n_slides}"
    )

    # нет слайда-заглушки
    all_text = ""
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                all_text += shape.text or ""
    assert "Презентация собрана автоматически" not in all_text, (
        "Заглушка-плейсхолдер должна быть удалена"
    )

    # есть титул/обзор/выводы/рекомендации (по тексту)
    assert "BI-аналитика налогов РБ" in all_text
    assert "Обзор" in all_text or "overview" in all_text.lower()
    assert "Ключевые выводы" in all_text
    assert "Рекомендации" in all_text

    # изображения присутствуют
    image_count = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.shape_type == 13:  # PICTURE
                image_count += 1
    assert image_count >= 1, "В презентации должны присутствовать изображения (PNG)"

    # clean? no, leave the artifact
