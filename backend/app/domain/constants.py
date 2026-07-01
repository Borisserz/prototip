"""Константы датасета и визуализации — единый источник для всех агентов."""

from __future__ import annotations

ALLOWED_COLUMNS: frozenset[str] = frozenset(
    {
        "period",
        "region",
        "tax_type",
        "accrued",
        "paid",
        "debt",
        "taxpayers",
        "penalties",
    }
)

CHART_TYPE_RU: dict[str, str] = {
    "bar": "столбчатой диаграмме",
    "grouped_bar": "группированной столбчатой диаграмме",
    "stacked_bar": "стековой столбчатой диаграмме",
    "line": "линейном графике",
    "area": "диаграмме с заливкой (area)",
    "scatter": "точечной диаграмме",
    "waterfall": "водопадной диаграмме",
    "horizontal_bar": "горизонтальной столбчатой диаграмме",
    "donut": "круговой (donut) диаграмме",
    "kpi": "KPI-индикаторе",
    "heatmap": "тепловой карте",
    "treemap": "древовидной диаграмме (treemap)",
}

# Агенты, запрещённые в под-планах (например, внутри presentation slide pipeline)
FORBIDDEN_SUBPLAN_AGENTS: frozenset[str] = frozenset({"presentation_agent", "planner_agent"})
