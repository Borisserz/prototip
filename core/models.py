"""Pydantic модели контрактов (Phase 1+).

ChartSpec — центральная спецификация для детерминированного построения графиков
в viz/charts.py. Все данные между модулями — только через Pydantic (никаких dict).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChartType = Literal[
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


class ChartSpec(BaseModel):
    """Спецификация графика (детерминированный рендер в viz/charts.py).

    Заполняется вручную в Phase1 тестах; позже ChartAgent (structured output, temperature=0).
    Поля: тип, заголовки (title / action_title), оси, цвет/группа, агрегация, источник,
    insights, rationale. Data Storytelling: action_title (говорящий вывод), show_average,
    highlight_category (акцент одной категории при single-series).
    """

    chart_type: ChartType = Field(..., description="Тип графика")
    title: str = Field(..., description="Заголовок на русском")
    subtitle: str | None = Field(None, description="Подзаголовок")
    x: str = Field(..., description="Ось X / категория (имя колонки в df)")
    y: str = Field(..., description="Ось Y / значение / мера (имя колонки в df)")
    color: str | None = Field(None, description="Группа / цвет / сегмент (имя колонки)")
    agg: Literal["sum", "mean", "count", "none"] | None = Field(
        "sum", description="Агрегация перед визуализацией"
    )
    source: str = Field(
        "Синтетические данные (демо), Республика Беларусь",
        description="Подпись источника (всегда на русском)",
    )
    insights: list[str] = Field(
        default_factory=list, description="3-5 ключевых выводов по графику (тезисы на русском)"
    )
    rationale: str = Field(
        ..., description="Почему выбран именно этот тип графика (аудит/пояснение)"
    )
    action_title: str | None = Field(
        None, description="Говорящий заголовок с бизнес-выводом (Data Storytelling)"
    )
    show_average: bool = Field(
        False, description="Отрисовать пунктирную линию среднего (сравнение категорий)"
    )
    highlight_category: str | None = Field(
        None, description="Категория для цветового акцента (только без color)"
    )
