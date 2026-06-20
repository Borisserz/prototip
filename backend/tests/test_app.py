"""Tests for FastAPI layer (app/main.py) via Orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from app.schemas import AskResult, DashboardResult, PresentationResult

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["phase"] == config.app_phase
    assert "version" in data


def test_root_informational() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "prototip" in response.json()["message"]


def test_404_for_unknown_path() -> None:
    response = client.get("/nonexistent/phase0/test")
    assert response.status_code == 404


def test_ask_endpoint():
    fake = AskResult(question="q", sql="SELECT 1", data=[], reasoning="ok")
    with patch("app.main.get_orchestrator") as mock_get:
        mock_orch = MagicMock()
        mock_orch.ask.return_value = fake
        mock_get.return_value = mock_orch
        resp = client.post("/ask", json={"question": "Топ регионов"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == "q"


def test_generate_presentation_endpoint():
    payload = {
        "mode": "По вопросам",
        "overall_theme": None,
        "questions": [
            {"text": "Топ-3 региона по задолженности", "chart_type": "horizontal_bar", "note": ""}
        ],
        "num_slides": 5,
        "include_title": True,
        "include_recommendations": True,
    }
    pres = PresentationResult(pptx_path="out/pres.pptx", num_slides=6, reasoning="mock")
    with patch("app.main.get_orchestrator") as mock_get:
        mock_orch = MagicMock()
        mock_orch.presentation.return_value = pres
        mock_get.return_value = mock_orch
        resp = client.post("/generate_presentation", json=payload)
    assert resp.status_code == 200
    assert resp.json()["num_slides"] == 6


def test_generate_dashboard_endpoint():
    payload = {
        "question": "Дашборд по задолженности по регионам",
        "max_charts": 3,
        "include_kpi": True,
        "data": None,
    }
    dash = DashboardResult(title="Дашборд тест", summary="summary", reasoning="test")
    with patch("app.main.get_orchestrator") as mock_get:
        mock_orch = MagicMock()
        mock_orch.dashboard.return_value = dash
        mock_get.return_value = mock_orch
        resp = client.post("/generate_dashboard", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Дашборд тест"