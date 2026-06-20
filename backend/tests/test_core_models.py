"""Тесты модели ChartSpec (core/models.py).

Проверяют создание, валидацию, русские поля, roundtrip (для structured output позже).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models import ChartSpec, ChartType


def test_chart_spec_minimal_valid_bar() -> None:
    """Минимально валидный spec для bar (как в тестах viz)."""
    spec = ChartSpec(
        chart_type="bar",
        title="Начисленные налоги по регионам",
        x="region",
        y="accrued",
        rationale="Сравнение категорий — классический bar",
    )
    assert spec.chart_type == "bar"
    assert spec.agg == "sum"  # default
    assert "Начисленные" in spec.title
    assert spec.source.startswith("Синтетические")


def test_chart_spec_with_all_fields_russian() -> None:
    """Полный spec с insights/rationale на русском, color, subtitle."""
    spec = ChartSpec(
        chart_type="line",
        title="Динамика начислений",
        subtitle="По всем регионам за 2024",
        x="period",
        y="accrued",
        color="region",
        agg="sum",
        source="Синтетические данные налогов",
        insights=["Рост в Q4", "г. Минск доминирует", "Подоходный налог стабилен"],
        rationale="Время → line (тренды и сезонность)",
    )
    assert spec.color == "region"
    assert len(spec.insights) == 3
    assert "line" in spec.rationale


def test_chart_spec_invalid_type_raises() -> None:
    """Невалидный chart_type ловится Pydantic."""
    with pytest.raises(ValidationError):
        ChartSpec(
            chart_type="pie",  # not in Literal
            title="Неверный",
            x="a",
            y="b",
            rationale="нет",
        )


def test_chart_spec_json_roundtrip_for_llm() -> None:
    """to_json / model_validate — готово для structured output LLM."""
    spec = ChartSpec(
        chart_type="donut",
        title="Структура по налогам",
        x="tax_type",
        y="accrued",
        agg="sum",
        rationale="Доли — donut",
    )
    data = spec.model_dump()
    restored = ChartSpec.model_validate(data)
    assert restored.title == spec.title
    assert restored.chart_type == "donut"


def test_chart_type_literal_contains_all_twelve() -> None:
    """ChartType покрывает 12 типов (Phase 1 + area/scatter/waterfall/treemap)."""
    types: list[ChartType] = [
        "bar",
        "grouped_bar",
        "stacked_bar",
        "line",
        "horizontal_bar",
        "donut",
        "kpi",
        "heatmap",
        "area",
        "scatter",
        "waterfall",
        "treemap",
    ]
    for t in types:
        ChartSpec(chart_type=t, title="t", x="x", y="y", rationale="r")
    assert len(types) == 12


def test_chart_spec_storytelling_fields_optional() -> None:
    """Data Storytelling поля опциональны и roundtrip-safe."""
    spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Задолженность по регионам",
        x="region",
        y="debt",
        rationale="рейтинг",
        action_title="Гомельская область — лидер по задолженности",
        show_average=True,
        highlight_category="Гомельская область",
    )
    restored = ChartSpec.model_validate(spec.model_dump())
    assert restored.action_title == spec.action_title
    assert restored.show_average is True
    assert restored.highlight_category == "Гомельская область"


def test_chart_spec_top_n_and_sort_order() -> None:
    spec = ChartSpec(
        chart_type="horizontal_bar",
        title="Топ-5",
        x="region",
        y="debt",
        rationale="рейтинг",
        top_n=5,
        sort_order="desc",
    )
    restored = ChartSpec.model_validate(spec.model_dump())
    assert restored.top_n == 5
    assert restored.sort_order == "desc"
