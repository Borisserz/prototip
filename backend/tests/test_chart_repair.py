"""Тесты детерминированного repair ChartSpec."""

from __future__ import annotations

import pandas as pd
import pytest

from app.chart_data_profile import format_profile_for_prompt, profile_data
from app.chart_repair import normalize_chart_spec, repair_chart_spec
from app.storytelling import enrich_data_explanation
from core.models import ChartSpec


@pytest.fixture(scope="module")
def sample_df() -> pd.DataFrame:
    return pd.read_csv("data/sample.csv")


def test_normalize_chart_spec_adds_storytelling_defaults() -> None:
    """Старые/урезанные spec из LLM получают highlight_category и прочие поля."""
    partial = {
        "chart_type": "donut",
        "title": "Структура",
        "x": "tax_type",
        "y": "accrued",
        "rationale": "доли",
    }
    spec = normalize_chart_spec(partial)
    assert spec.highlight_category is None
    assert spec.show_average is False
    assert spec.action_title is None
    assert hasattr(spec, "highlight_category")


def test_repair_resolves_metric_aliases(sample_df: pd.DataFrame) -> None:
    data = sample_df.to_dict(orient="records")
    spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Топ",
        x="region",
        y="total_debt",
        rationale="test",
    )
    repaired = repair_chart_spec(spec, data, question="Топ-3 региона по задолженности")
    assert repaired.y == "debt"
    assert repaired.top_n == 3
    assert repaired.sort_order == "desc"


def test_repair_swaps_horizontal_bar_axes(sample_df: pd.DataFrame) -> None:
    data = sample_df.to_dict(orient="records")
    spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Топ",
        x="debt",
        y="region",
        rationale="test",
    )
    repaired = repair_chart_spec(spec, data)
    assert repaired.x == "region"
    assert repaired.y == "debt"


def test_repair_fallback_action_title(sample_df: pd.DataFrame) -> None:
    data = sample_df.to_dict(orient="records")
    spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Рейтинг",
        x="region",
        y="debt",
        rationale="test",
    )
    repaired = repair_chart_spec(spec, data, question="Топ регионов по задолженности")
    assert repaired.action_title
    assert (
        "Br" in repaired.action_title
        or "млрд" in repaired.action_title
        or "млн" in repaired.action_title
    )


def test_profile_data_has_penalties(sample_df: pd.DataFrame) -> None:
    data = sample_df.head(20).to_dict(orient="records")
    prof = profile_data(data)
    assert "penalties" in prof.get("metrics", {})
    text = format_profile_for_prompt(prof)
    assert "penalties" in text


def test_enrich_data_explanation_ru() -> None:
    spec = ChartSpec(
        chart_type="bar",
        title="t",
        x="region",
        y="accrued",
        agg="sum",
        rationale="r",
    )
    expl = enrich_data_explanation(
        spec=spec,
        drilldown_filters={"region": "г. Минск"},
        row_count=42,
    )
    assert "г. Минск" in expl
    assert "42" in expl
