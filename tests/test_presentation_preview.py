"""Tests for presentation carousel path collection."""

from __future__ import annotations

from pathlib import Path

from app.agents.models import PresentationResult
from ui.streamlit_app import _collect_presentation_preview_paths, _presentation_carousel_state_key


def test_collect_preview_paths_no_glob_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ui.streamlit_app.PROJECT_ROOT",
        tmp_path,
    )
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "pres_slide_old_run_0_test.png"
    stale.write_bytes(b"fake")

    res = PresentationResult(pptx_path="out/presentation.pptx", num_slides=3, slide_png_paths=[])
    paths = _collect_presentation_preview_paths(res)
    assert paths == []


def test_collect_preview_paths_from_result(tmp_path, monkeypatch):
    monkeypatch.setattr("ui.streamlit_app.PROJECT_ROOT", tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    png = out / "pres_slide_abc_0_chart.png"
    png.write_bytes(b"fake")

    res = PresentationResult(
        pptx_path=str(out / "presentation.pptx"),
        num_slides=2,
        slide_png_paths=[str(png)],
        presentation_id="abc",
    )
    paths = _collect_presentation_preview_paths(res)
    assert len(paths) == 1
    assert paths[0].name == "pres_slide_abc_0_chart.png"


def test_carousel_state_key_stable():
    p1 = [Path("/a/1.png"), Path("/a/2.png")]
    k1 = _presentation_carousel_state_key(p1, "chat")
    k2 = _presentation_carousel_state_key(p1, "chat")
    assert k1 == k2