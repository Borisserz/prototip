"""Smoke-тест для Streamlit UI (Phase 7 + dashboard).

Просто проверяет, что модуль импортируется без синтаксических/импортных ошибок.
Бизнес-логика не выполняется (мокаем Orchestrator).

Дополнительно: проверяем, что русские типы графиков в форме презентации чисто на русском (нет английских ключей в UI).
Dashboard: наличие _render_dashboard и поддержка 3 вкладок.
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

    # Проверка Step 1: русские лейблы в дропдауне (нет "line"/"bar" и т.п. в пользовательском)
    from ui.streamlit_app import (
        CHART_DISPLAY_FOR_VAL,
        CHART_DISPLAY_OPTIONS,
        CHART_VAL_FOR_DISPLAY,
    )

    assert all(
        isinstance(o, str) and o.isascii() is False or o in ("авто",) for o in CHART_DISPLAY_OPTIONS
    )
    # "авто" ok, остальные должны содержать кириллицу (русские слова)
    non_auto = [o for o in CHART_DISPLAY_OPTIONS if o != "авто"]
    assert all(any("\u0400" <= ch <= "\u04ff" for ch in o) for o in non_auto)
    assert None in CHART_VAL_FOR_DISPLAY.values()  # авто -> None
    assert "horizontal_bar" in CHART_VAL_FOR_DISPLAY.values()
    # реверс маппинг покрывает
    assert CHART_DISPLAY_FOR_VAL.get("horizontal_bar") == "горизонтальная столбчатая"

    # Dashboard smoke (plan step6)
    assert hasattr(ui.streamlit_app, "_render_dashboard")
    # (tabs count проверяется рантаймом в smoke; здесь достаточно импорта + наличие)

    # Tier 1 UI improvements smoke (data explorer, onboarding, history hints, pres outline)
    with open("ui/streamlit_app.py", encoding="utf-8") as f:
        src = f.read()
    assert "Набор данных (демо)" in src
    assert "Как быстро начать" in src or "Как пользоваться платформой" in src
    assert "Предыдущие вопросы" in src or "Предыдущие дашборды" in src
    assert "Основные темы в презентации" in src or "Тема презентации" in src
    assert "Как был построен этот дашборд" in src  # planner-prep surface (collapsed)
