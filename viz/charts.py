"""Фабрика графиков (Phase 1).

Единственная точка построения: build_chart(df, ChartSpec) -> go.Figure
+ экспорт PNG (kaleido, высокое качество для слайдов) и HTML.
Все графики проходят apply_common_style из .style (никаких цветов/шрифтов здесь).

НИКОГДА не exec код от LLM.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.models import ChartSpec

from .style import (
    CHART_HEIGHT,
    CHART_WIDTH,
    apply_common_style,
    format_number_ru,
    get_russian_label,
)


def _prepare_agg(df: pd.DataFrame, spec: ChartSpec) -> pd.DataFrame:
    """Внутренняя агрегация по spec.agg (если не none). Возвращает копию/агг df."""
    if not spec.agg or spec.agg == "none":
        return df.copy()

    group_cols: list[str] = [spec.x]
    if spec.color:
        group_cols.append(spec.color)

    ycol = spec.y
    if ycol not in df.columns:
        raise ValueError(f"Колонка y='{ycol}' отсутствует в df для агрегации")

    if spec.agg == "sum":
        return df.groupby(group_cols, as_index=False)[ycol].sum()
    if spec.agg == "mean":
        return df.groupby(group_cols, as_index=False)[ycol].mean()
    if spec.agg == "count":
        out = df.groupby(group_cols, as_index=False).size().rename(columns={"size": ycol})
        return out
    return df.copy()


def build_chart(df: pd.DataFrame, spec: ChartSpec) -> go.Figure:
    """Главная фабрика. Возвращает plotly Figure в едином стиле.

    Выполняет валидацию колонок, агрегацию, dispatch по 8 типам, apply style.
    """
    if df.empty:
        raise ValueError("Пустой DataFrame передан в build_chart")

    cols_to_check = [spec.y]
    if spec.chart_type != "kpi":
        cols_to_check.append(spec.x)
    for col in cols_to_check:
        if col not in df.columns:
            raise ValueError(f"Колонка '{col}' (x/y) отсутствует в df для {spec.chart_type}")

    ctype = spec.chart_type
    x, y, color = spec.x, spec.y, spec.color

    dff = df[[y]].copy() if ctype == "kpi" else _prepare_agg(df, spec)  # no group for kpi

    fig: go.Figure

    if ctype == "bar" or ctype == "grouped_bar":
        fig = px.bar(dff, x=x, y=y, color=color, barmode="group")
    elif ctype == "stacked_bar":
        fig = px.bar(dff, x=x, y=y, color=color, barmode="stack")
    elif ctype == "line":
        fig = px.line(dff, x=x, y=y, color=color, markers=True)
    elif ctype == "horizontal_bar":
        # Для horizontal_bar: категория (регион) на Y, значение на X (orientation h)
        # Сортируем по убыванию, чтобы largest на top (для "Топ-N")
        if color is None and len(dff) > 1:
            dff = dff.sort_values(y, ascending=False)
        fig = px.bar(dff, x=y, y=x, color=color, orientation="h")
    elif ctype == "donut":
        fig = px.pie(dff, names=x, values=y, hole=0.55)
        fig.update_traces(textinfo="percent+label")
    elif ctype == "kpi":
        # KPI: берём сумму/значение по y (после agg)
        total = float(dff[y].sum()) if spec.agg != "none" else float(dff[y].iloc[0])
        label = get_russian_label(y)
        fig = go.Figure(
            go.Indicator(
                mode="number",
                value=total,
                number={
                    "valueformat": ",",
                    "font": {"size": 68, "color": "#E69F00"},
                    "prefix": "",
                },
                title={"text": f"{spec.title}<br><span style='font-size:0.6em'>{label}</span>"},
            )
        )
        # Стиль карточки
        fig.update_layout(
            width=CHART_WIDTH // 2,
            height=CHART_HEIGHT // 2 + 80,
            paper_bgcolor="#F8F8F8",
            margin=dict(l=20, r=20, t=30, b=20),
        )
    elif ctype == "heatmap":
        # pivot: x и color как измерения, y — значение
        if color is None:
            color = x  # fallback, но лучше caller даёт
        pivot = dff.pivot_table(index=x, columns=color, values=y, aggfunc="sum").fillna(0)
        fig = go.Figure(
            go.Heatmap(
                z=pivot.values,
                x=list(pivot.columns),
                y=list(pivot.index),
                colorscale="Blues",
                colorbar=dict(title=get_russian_label(y)),
            )
        )
        fig.update_layout(
            xaxis_title=get_russian_label(str(color)), yaxis_title=get_russian_label(x)
        )
    else:
        raise ValueError(f"Неизвестный chart_type: {ctype}")

    # Value labels on bars (подировка: русские числа с Br, цвет из палитры уже в style)
    if ctype in ("bar", "grouped_bar", "stacked_bar", "horizontal_bar"):
        try:
            if y in dff.columns:
                texts = [format_number_ru(v, suffix="Br") for v in dff[y]]
                fig.update_traces(text=texts, textposition="outside", textfont=dict(size=9))
        except Exception:
            pass  # non-fatal

    # Общий стиль (кроме kpi — частично переопределён выше)
    if ctype != "kpi":
        fig = apply_common_style(fig, spec)

    # Для horizontal_bar оси в фигуре swapped по смыслу (категория на Y, значение на X),
    # поэтому переопределяем titles после apply (который использует spec x/y без учёта swap)
    if ctype == "horizontal_bar":
        fig.update_layout(
            xaxis_title=get_russian_label(y),
            yaxis_title=get_russian_label(x),
        )

    # Hover с русским форматом для чисел (упрощённо)
    if ctype in {"bar", "grouped_bar", "stacked_bar", "line", "horizontal_bar"}:
        for trace in fig.data:
            if hasattr(trace, "hovertemplate") and trace.hovertemplate:
                # plotly сам использует :, но мы оставляем; при необходимости post-process
                pass

    # Фиксируем размер для экспорта (kpi уже свой)
    if ctype != "kpi":
        fig.update_layout(width=CHART_WIDTH, height=CHART_HEIGHT)

    return fig


def export_png(
    fig: go.Figure,
    path: str | Path,
    width: int | None = None,
    height: int | None = None,
    scale: float = 2.0,
) -> Path:
    """Экспорт PNG высокого качества (для презентаций/слайдов)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    w = width or CHART_WIDTH
    h = height or CHART_HEIGHT
    fig.write_image(str(p), width=w, height=h, scale=scale)
    return p


def export_html(fig: go.Figure, path: str | Path, include_plotlyjs: str = "cdn") -> Path:
    """Экспорт интерактивного HTML."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(p), include_plotlyjs=include_plotlyjs, full_html=True)
    return p
