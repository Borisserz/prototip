"""Детерминированное обогащение Data Storytelling полей."""

from __future__ import annotations

from typing import Any

from core.models import ChartSpec
from viz.style import get_russian_label


def enrich_data_explanation(
    *,
    sql: str | None = None,
    drilldown_filters: dict[str, str] | None = None,
    spec: ChartSpec | dict[str, Any] | None = None,
    row_count: int = 0,
) -> str:
    parts: list[str] = []
    if drilldown_filters:
        fl = ", ".join(f"{get_russian_label(k)}: {v}" for k, v in drilldown_filters.items())
        parts.append(f"Данные отфильтрованы ({fl})")
    if spec:
        s = spec if isinstance(spec, ChartSpec) else ChartSpec.model_validate(spec)
        agg_ru = {
            "sum": "суммой",
            "mean": "средним",
            "count": "количеством",
            "none": "без агрегации",
        }
        agg = agg_ru.get(str(s.agg or "sum"), "суммой")
        parts.append(
            f"Сгруппировано по «{get_russian_label(s.x)}»"
            + (f" и «{get_russian_label(s.color)}»" if s.color else "")
            + f", агрегировано {agg}"
        )
    if row_count:
        parts.append(f"в выборке {row_count} строк")
    if not parts and sql:
        return "Данные получены SQL-запросом к демо-датасету налогов РБ."
    return ". ".join(parts) + "." if parts else ""


def enrich_analysis_explanation(
    analysis: Any,
    *,
    sql: str | None = None,
    drilldown_filters: dict[str, str] | None = None,
    spec: ChartSpec | dict[str, Any] | None = None,
    row_count: int = 0,
) -> Any:
    """Дополняет AnalysisResult.data_explanation если LLM не заполнил."""
    if getattr(analysis, "data_explanation", None):
        return analysis
    expl = enrich_data_explanation(
        sql=sql,
        drilldown_filters=drilldown_filters,
        spec=spec,
        row_count=row_count,
    )
    if expl and hasattr(analysis, "model_copy"):
        return analysis.model_copy(update={"data_explanation": expl})
    return analysis
