"""Smoke-тесты leadership showcase (каталог + офлайн-сборка)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.showcase_builder import (
    build_offline_presentation,
    catalog_by_chart_type,
    export_chart_assets,
    generate_showcase,
    load_base_dataset,
    prepare_entry_df,
)
from app.showcase_catalog import chart_showcase_entries, presentation_bundles


def test_catalog_has_twelve_chart_types():
    entries = chart_showcase_entries()
    assert len(entries) == 12
    slugs = {e.slug for e in entries}
    assert slugs == {
        "bar",
        "grouped_bar",
        "stacked_bar",
        "line",
        "area",
        "scatter",
        "waterfall",
        "horizontal_bar",
        "donut",
        "kpi",
        "heatmap",
        "treemap",
    }


def test_catalog_has_four_presentations():
    bundles = presentation_bundles()
    assert len(bundles) == 4
    filenames = {b.filename for b in bundles}
    assert "01_obzor_nalogov_RB.pptx" in filenames
    assert "04_kompleksny_analiticheskiy.pptx" in filenames


def test_catalog_by_chart_type_covers_all_slugs():
    catalog = catalog_by_chart_type()
    assert len(catalog) == 12
    for entry in chart_showcase_entries():
        assert entry.slug in catalog


@pytest.mark.skipif(
    not Path("data/sample.csv").exists(),
    reason="data/sample.csv отсутствует",
)
def test_export_single_chart_asset(tmp_path: Path):
    base_df = load_base_dataset()
    entry = chart_showcase_entries()[0]
    df = prepare_entry_df(entry, base_df)
    out_dir = tmp_path / "01_bar"
    assets = export_chart_assets(entry, df, out_dir, scale=1.0, manifest_base=tmp_path)
    assert (tmp_path / assets["png"]).exists()
    assert (tmp_path / assets["png"]).stat().st_size > 5000
    assert (tmp_path / assets["html"]).exists()
    assert (tmp_path / assets["spec"]).exists()


@pytest.mark.skipif(
    not Path("data/sample.csv").exists(),
    reason="data/sample.csv отсутствует",
)
def test_offline_presentation_smoke(tmp_path: Path):
    base_df = load_base_dataset()
    bundle = presentation_bundles()[0]
    out_pptx = tmp_path / bundle.filename
    meta = build_offline_presentation(bundle, base_df, out_pptx)
    assert out_pptx.exists() and out_pptx.stat().st_size > 10_000
    assert meta["num_slides"] == bundle.num_slides
    assert meta["questions"] >= 1


@pytest.mark.skipif(
    not Path("data/sample.csv").exists(),
    reason="data/sample.csv отсутствует",
)
def test_generate_showcase_integration(tmp_path: Path):
    manifest = generate_showcase(tmp_path, chart_scale=1.0)
    assert (tmp_path / "manifest.json").exists()
    assert len(manifest["charts"]) == 12
    assert len(manifest["presentations"]) == 4
    for ch in manifest["charts"]:
        assert (tmp_path / ch["png"]).exists()
        assert (tmp_path / ch["html"]).exists()
        assert "/" not in ch["png"] or not ch["png"].startswith("/")
    for pres in manifest["presentations"]:
        assert (tmp_path / pres["pptx"]).exists()
        assert "slide_pngs" not in pres