"""Детерминированный repair ChartSpec после LLM (spec-first)."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from core.models import ChartSpec
from viz.style import format_number_ru

logger = logging.getLogger("ChartRepair")


def normalize_chart_spec(spec: ChartSpec | dict[str, Any]) -> ChartSpec:
    """Приводит ChartSpec к актуальной схеме (все storytelling-поля с дефолтами)."""
    if isinstance(spec, ChartSpec):
        return ChartSpec.model_validate(spec.model_dump())
    return ChartSpec.model_validate(spec)


DIMENSION_COLS = frozenset({"region", "tax_type", "period"})
METRIC_ALIASES: dict[str, str] = {
    "total_debt": "debt",
    "debt_total": "debt",
    "sum_debt": "debt",
    "total_accrued": "accrued",
    "sum_accrued": "accrued",
    "total_paid": "paid",
    "sum_paid": "paid",
}
_MULTI_SERIES_TYPES = frozenset({"grouped_bar", "stacked_bar"})


def _cols(data: list[dict]) -> set[str]:
    return set(data[0].keys()) if data else set()


def _resolve_col(name: str | None, cols: set[str]) -> str | None:
    if not name:
        return name
    if name in cols:
        return name
    low = name.lower().strip()
    if low in METRIC_ALIASES and METRIC_ALIASES[low] in cols:
        return METRIC_ALIASES[low]
    for alias, canonical in METRIC_ALIASES.items():
        if alias in low and canonical in cols:
            return canonical
    for c in cols:
        if c.lower() == low:
            return c
    return name


def _is_numeric_col(data: list[dict], col: str) -> bool:
    if not data or col not in data[0]:
        return False
    for row in data[:20]:
        v = row.get(col)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return True
        if v is not None:
            try:
                float(v)
                return True
            except (TypeError, ValueError):
                return False
    return False


def _is_dimension_col(col: str) -> bool:
    return col.lower().strip() in DIMENSION_COLS


def _parse_top_n(question: str) -> int | None:
    m = re.search(r"топ[-\s]?(\d+)", question.lower())
    return int(m.group(1)) if m else None


def _fallback_action_title(spec: ChartSpec, data: list[dict], question: str) -> str | None:
    if spec.action_title or not data:
        return spec.action_title
    q = question.lower()
    ranking = any(k in q for k in ("топ", "наибольш", "рейтинг", "лидер", "максим"))
    if not ranking and spec.chart_type not in ("horizontal_bar", "bar"):
        return None
    try:
        df = pd.DataFrame(data)
        y = spec.y if spec.y in df.columns else _resolve_col(spec.y, set(df.columns))
        x = spec.x if spec.x in df.columns else _resolve_col(spec.x, set(df.columns))
        if y not in df.columns or x not in df.columns:
            return None
        agg = spec.agg or "sum"
        if agg == "sum":
            g = df.groupby(x, as_index=False)[y].sum()
        elif agg == "mean":
            g = df.groupby(x, as_index=False)[y].mean()
        else:
            g = df
        if g.empty:
            return None
        idx = g[y].idxmax()
        row = g.loc[idx]
        cat = str(row[x])
        val = float(row[y])
        suffix = (
            "бел. руб."
            if any(k in str(y).lower() for k in ("debt", "accrued", "paid", "penalties"))
            else ""
        )
        return f"{cat} — лидер ({format_number_ru(val, suffix=suffix)})"
    except Exception:
        return None


def repair_chart_spec(spec: ChartSpec, data: list[dict], question: str = "") -> ChartSpec:
    """Чинит и обогащает ChartSpec перед build_chart."""
    spec = normalize_chart_spec(spec)
    if not data:
        return spec

    cols = _cols(data)
    updates: dict[str, Any] = {}

    x = _resolve_col(spec.x, cols)
    y = _resolve_col(spec.y, cols)
    color = _resolve_col(spec.color, cols) if spec.color else None

    if x != spec.x:
        updates["x"] = x
    if y != spec.y:
        updates["y"] = y
    if color != spec.color:
        updates["color"] = color

    # horizontal_bar: swap если x числовая, y категориальная
    if spec.chart_type == "horizontal_bar":
        x_num = _is_numeric_col(data, x or spec.x)
        y_dim = _is_dimension_col(y or spec.y)
        if x_num and y_dim:
            updates["x"] = y
            updates["y"] = x
            logger.info("[ChartRepair] swapped x/y for horizontal_bar")

    highlight = getattr(spec, "highlight_category", None)
    if highlight and (updates.get("color") or spec.color):
        updates["highlight_category"] = None
        logger.info("[ChartRepair] cleared highlight_category (color set)")

    if spec.show_average and spec.chart_type in _MULTI_SERIES_TYPES:
        updates["show_average"] = False

    top_n = spec.top_n or _parse_top_n(question)
    if top_n and top_n > 0:
        updates["top_n"] = top_n

    if not spec.sort_order:
        x_col = (updates.get("x") or spec.x or "").lower()
        if x_col == "period":
            updates["sort_order"] = "asc"
        elif spec.chart_type == "horizontal_bar":
            updates["sort_order"] = "desc"

    action = _fallback_action_title(
        spec.model_copy(update=updates) if updates else spec,
        data,
        question,
    )
    if action and not spec.action_title:
        updates["action_title"] = action

    if updates:
        spec = spec.model_copy(update=updates)
    return spec
