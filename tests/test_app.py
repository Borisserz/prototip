"""Tests for Phase 0 FastAPI skeleton (app/main.py).

Covers health endpoint and basic routing. Uses TestClient (no real server needed).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    """GET /health must return 200 and status ok + phase 0 (per Phase 0 Готово)."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["phase"] == "0"


def test_health_has_no_extra_keys_minimal() -> None:
    """Health response shape is minimal and stable."""
    response = client.get("/health")
    data = response.json()
    assert set(data.keys()) == {"status", "phase"}


def test_root_informational() -> None:
    """GET / returns informational message (not required but useful)."""
    response = client.get("/")
    assert response.status_code == 200
    assert "prototip" in response.json()["message"]


def test_404_for_unknown_path() -> None:
    """Unknown paths return 404 (standard FastAPI behavior)."""
    response = client.get("/nonexistent/phase0/test")
    assert response.status_code == 404


def test_generate_presentation_endpoint():
    """POST /generate_presentation принимает payload и возвращает результат (мок агента)."""
    from unittest.mock import MagicMock, patch

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

    with patch("app.agents.presentation_agent.PresentationAgent") as mock_pa:
        mock_instance = MagicMock()
        mock_instance.run.return_value = MagicMock(pptx_path="out/pres.pptx", num_slides=6)
        mock_pa.return_value = mock_instance

        resp = client.post("/generate_presentation", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "pptx_path" in data
        assert data["num_slides"] >= 3
