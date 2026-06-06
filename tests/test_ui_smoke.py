"""Smoke-тест для Streamlit UI (chat + pinned dashboard + pipeline)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_ui_streamlit_app_imports_without_error():
    """Импорт ui/streamlit_app.py должен проходить без ошибок."""
    with patch("app.orchestrator.Orchestrator") as mock_orchestrator:
        mock_orchestrator.return_value = MagicMock()
        import ui.streamlit_app  # noqa: F401

    assert hasattr(ui.streamlit_app, "main")
    assert callable(ui.streamlit_app.main)

    from app.drilldown import DRILLDOWN_DIMENSIONS
    from ui.streamlit_app import (
        CHART_DISPLAY_FOR_VAL,
        CHART_DISPLAY_OPTIONS,
        CHART_VAL_FOR_DISPLAY,
    )
    from ui.components.pipeline import pipeline_step_markdown, update_pipeline_live_ui
    from ui.components.trace import render_planner_trace

    assert "авто" in CHART_DISPLAY_OPTIONS
    assert "region" in DRILLDOWN_DIMENSIONS
    assert callable(pipeline_step_markdown)
    assert callable(update_pipeline_live_ui)
    assert callable(render_planner_trace)

    with open("ui/streamlit_app.py", encoding="utf-8") as f:
        src = f.read()

    assert hasattr(ui.streamlit_app, "_render_dashboard")
    assert hasattr(ui.streamlit_app, "_render_presentation_carousel")
    assert "Мой дашборд" in src
    assert "PROMPT_CARD_CATEGORIES" in src
    assert "main_messages" in src
    assert "orch.ask" in src or "ask(prompt" in src or "_run_query" in src
    assert "get_orchestrator().presentation" in src
    assert "render_planner_trace" in src
    assert "pinned_items" in src
    assert "pipeline_store" in src
    assert "Сбросить детализацию" in src
    assert "_render_unified_action_bar" in src
    assert "GOV_DISCLAIMER" in src
    assert None in CHART_VAL_FOR_DISPLAY.values()