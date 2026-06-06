"""Drill-down domain logic (извлечение фильтров из Plotly, вопросы, контекст)."""

from __future__ import annotations

import hashlib
from typing import Any

from app.schemas import ChartSpec, DrilldownContext

DRILLDOWN_DIMENSIONS: dict[str, str] = {
    "region": "Регион",
    "tax_type": "Вид налога",
    "period": "Период",
}


def extract_drilldown_from_point(
    point: dict[str, Any],
    chart_spec: ChartSpec,
) -> dict[str, str]:
    """Извлекает фильтр (region / tax_type / period) из выбранной точки Plotly."""
    filters: dict[str, str] = {}
    x_val = point.get("x")
    y_val = point.get("y")
    legend = point.get("legendgroup") or point.get("name") or point.get("text")

    if chart_spec.chart_type in ("donut", "pie"):
        label = point.get("label") or point.get("text")
        if label and chart_spec.x in DRILLDOWN_DIMENSIONS:
            filters[chart_spec.x] = str(label)
        elif label:
            filters["_segment"] = str(label)
    elif chart_spec.chart_type == "horizontal_bar":
        if chart_spec.y in DRILLDOWN_DIMENSIONS and y_val is not None:
            filters[chart_spec.y] = str(y_val)
        elif chart_spec.x in DRILLDOWN_DIMENSIONS and x_val is not None:
            filters[chart_spec.x] = str(x_val)
    elif chart_spec.x in DRILLDOWN_DIMENSIONS and x_val is not None:
        filters[chart_spec.x] = str(x_val)

    if chart_spec.color and chart_spec.color in DRILLDOWN_DIMENSIONS and legend:
        filters[chart_spec.color] = str(legend)

    if not filters and x_val is not None:
        filters["_segment"] = str(x_val)
    elif not filters and y_val is not None:
        filters["_segment"] = str(y_val)

    return filters


def drilldown_context_from_selection(
    selection: Any,
    chart_spec: ChartSpec,
    *,
    chart_key: str,
) -> dict[str, Any] | None:
    """Строит drilldown_context из Plotly selection state."""
    if selection is None:
        return None
    sel = (
        selection.get("selection", selection)
        if isinstance(selection, dict)
        else getattr(selection, "selection", None)
    )
    if sel is None:
        return None
    points = sel.get("points", []) if isinstance(sel, dict) else []
    if not points:
        return None

    filters = extract_drilldown_from_point(points[0], chart_spec)
    if not filters:
        return None

    primary_dim = next((d for d in DRILLDOWN_DIMENSIONS if d in filters), "_segment")
    segment_label = filters.get(primary_dim, next(iter(filters.values())))

    return {
        "filters": filters,
        "dimension": primary_dim,
        "segment_label": segment_label,
        "source_chart_key": chart_key,
        "chart_title": chart_spec.title,
    }


def drilldown_context_fingerprint(ctx: dict[str, Any] | None) -> str:
    if not ctx:
        return ""
    return hashlib.sha256(
        f"{ctx.get('source_chart_key')}|{ctx.get('dimension')}|{ctx.get('segment_label')}|{ctx.get('filters')}".encode(
            "utf-8"
        )
    ).hexdigest()[:20]


def format_drilldown_trail(trail: list[dict[str, Any]]) -> str:
    if not trail:
        return ""
    parts = []
    for step in trail:
        dim = step.get("dimension", "")
        label = DRILLDOWN_DIMENSIONS.get(dim, dim) if dim in DRILLDOWN_DIMENSIONS else "Сегмент"
        parts.append(f"{label}: {step.get('label', step.get('value', ''))}")
    return " → ".join(parts)


def build_drilldown_question(ctx: dict[str, Any], trail: list[dict[str, Any]]) -> str:
    segment = ctx.get("segment_label") or "выбранному сегменту"
    question = f"Детальный анализ налогов по {segment}"
    trail_text = format_drilldown_trail(trail)
    if trail_text:
        question = f"{question} (контекст детализации: {trail_text})"
    return question


def build_detailed_analysis_question(segment: str) -> str:
    return f"Сделай детальный анализ (структура и тренды) для: {segment}"


def session_drilldown_context(
    pending_raw: Any,
    drilldown_context: Any,
    drilldown_trail: list[dict[str, Any]] | None,
) -> DrilldownContext | None:
    """Собирает DrilldownContext из session_state (UI-agnostic helper)."""
    if pending_raw is None:
        if not isinstance(drilldown_context, dict) or not drilldown_context.get("filters"):
            return None
        trail = drilldown_trail or []
        return DrilldownContext(
            filters=dict(drilldown_context.get("filters") or {}),
            dimension=str(drilldown_context.get("dimension") or "_segment"),
            segment_label=str(drilldown_context.get("segment_label") or ""),
            trail=[{k: str(v) for k, v in step.items()} for step in trail if isinstance(step, dict)],
        )
    if isinstance(pending_raw, DrilldownContext):
        return pending_raw
    if isinstance(pending_raw, dict):
        return DrilldownContext.model_validate(pending_raw)
    return None