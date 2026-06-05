"""Smoke-тест для Streamlit UI (Phase 7).

Просто проверяет, что модуль импортируется без синтаксических/импортных ошибок.
Бизнес-логика не выполняется (мокаем Orchestrator).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_ui_streamlit_app_imports_without_error():
    """Импорт ui/streamlit_app.py должен проходить без ошибок."""
    with (
        patch("app.orchestrator.Orchestrator") as mock_orchestrator,
        patch("app.agents.presentation_agent.PresentationAgent") as mock_presentation,
    ):
        # Возвращаем фейковые объекты, чтобы не тянуть реальные агенты/модель при импорте
        mock_instance = MagicMock()
        mock_orchestrator.return_value = mock_instance
        mock_presentation.return_value = MagicMock()

        # Сам импорт — это и есть smoke-тест на сборку модуля
        import ui.streamlit_app  # noqa: F401

    # Дополнительно: убеждаемся, что main определена (структура UI на месте)
    assert hasattr(ui.streamlit_app, "main")
    assert callable(ui.streamlit_app.main)
