"""Фабрика графиков (Phase 1).

Единственная точка построения: build_chart(df, ChartSpec) -> go.Figure
+ экспорт PNG (kaleido, высокое качество для слайдов) и HTML.
Все графики проходят apply_common_style из .style (никаких цветов/шрифтов здесь).

НИКОГДА не exec код от LLM.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.models import ChartSpec

from .style import (
    CHART_HEIGHT,
    CHART_WIDTH,
    MUTED_BAR_COLOR,
    PALETTE,
    apply_common_style,
    format_number_ru,
    get_russian_label,
    make_ru_ticktext,
)

_BAR_TYPES = frozenset({"bar", "grouped_bar", "stacked_bar", "horizontal_bar"})
_AVERAGE_TYPES = frozenset({"bar", "line", "area", "horizontal_bar"})


def _annotate_max_point(fig: go.Figure, dff: pd.DataFrame, spec: ChartSpec, ctype: str) -> None:
    """Стрелка на максимум для bar / horizontal_bar / line (говорящий график)."""
    try:
        if ctype not in ("bar", "horizontal_bar", "line"):
            return
        val_col, cat_col = spec.y, spec.x
        if val_col not in dff.columns or cat_col not in dff.columns:
            return
        numeric = pd.to_numeric(dff[val_col], errors="coerce")
        if numeric.isna().all():
            return
        idx = numeric.idxmax()
        row = dff.loc[idx]
        max_val = float(row[val_col])

        if ctype == "horizontal_bar":
            ann_x, ann_y = max_val, row[cat_col]
            ax, ay = -55, 0
        else:
            ann_x, ann_y = row[cat_col], max_val
            ax, ay = 0, -48

        fig.add_annotation(
            x=ann_x,
            y=ann_y,
            text="Максимум",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.5,
            arrowcolor="#D55E00",
            ax=ax,
            ay=ay,
            font=dict(family="Arial", size=10, color="#D55E00"),
            bgcolor="rgba(255, 248, 240, 0.95)",
            bordercolor="#D55E00",
            borderwidth=1,
            borderpad=4,
        )
    except Exception:
        pass


def _money_suffix(y_col: str) -> bool:
    return any(k in str(y_col).lower() for k in ("debt", "accrued", "paid")) and "taxpayer" not in str(
        y_col
    ).lower()


def _apply_bar_rounding(fig: go.Figure, ctype: str) -> None:
    if ctype not in _BAR_TYPES:
        return
    with suppress(Exception):
        fig.update_traces(marker_cornerradius=6)


def _category_col_for_highlight(spec: ChartSpec, ctype: str) -> str:
    # Категориальная колонка в df всегда spec.x (для hbar она на оси Y, но в данных — spec.x)
    return spec.x


def _apply_highlight(fig: go.Figure, dff: pd.DataFrame, spec: ChartSpec, ctype: str) -> bool:
    """Подсветка одной категории. Возвращает True, если цвета применены."""
    if not spec.highlight_category or spec.color is not None:
        return False
    if ctype not in _BAR_TYPES:
        return False

    cat_col = _category_col_for_highlight(spec, ctype)
    if cat_col not in dff.columns:
        return False

    target = str(spec.highlight_category).strip().lower()
    colors: list[str] = []
    matched = False
    for val in dff[cat_col]:
        if str(val).strip().lower() == target:
            colors.append(PALETTE[0])
            matched = True
        else:
            colors.append(MUTED_BAR_COLOR)

    if not matched:
        return False

    with suppress(Exception):
        fig.update_traces(marker_color=colors, marker=dict(color=colors, cornerradius=6))
    return True


def _apply_average_line(fig: go.Figure, dff: pd.DataFrame, spec: ChartSpec, ctype: str) -> None:
    if not spec.show_average or ctype not in _AVERAGE_TYPES:
        return
    if spec.y not in dff.columns:
        return

    numeric = pd.to_numeric(dff[spec.y], errors="coerce").dropna()
    if numeric.empty:
        return

    avg = float(numeric.mean())
    suffix = "Br" if _money_suffix(spec.y) else ""
    label = f"Среднее: {format_number_ru(avg, suffix=suffix)}"

    if ctype == "horizontal_bar":
        fig.add_vline(
            x=avg,
            line_dash="dash",
            line_color=PALETTE[1],
            annotation_text=label,
            annotation_position="top",
            annotation_font=dict(size=10, color=PALETTE[1]),
        )
    else:
        fig.add_hline(
            y=avg,
            line_dash="dash",
            line_color=PALETTE[1],
            annotation_text=label,
            annotation_position="right",
            annotation_font=dict(size=10, color=PALETTE[1]),
        )


def _build_treemap(dff: pd.DataFrame, spec: ChartSpec) -> go.Figure:
    path_cols = [spec.x]
    if spec.color and spec.color in dff.columns:
        path_cols.append(spec.color)
    return px.treemap(
        dff,
        path=path_cols,
        values=spec.y,
        color=spec.y,
        color_continuous_scale="Blues",
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
    if spec.chart_type not in ("kpi",):
        cols_to_check.append(spec.x)
    if spec.chart_type == "treemap" and spec.color:
        cols_to_check.append(spec.color)
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
    elif ctype == "area":
        fig = px.area(dff, x=x, y=y, color=color)
    elif ctype == "scatter":
        fig = px.scatter(dff, x=x, y=y, color=color)
    elif ctype == "waterfall":
        # Basic waterfall using relative bars or go.Waterfall.
        # For demo, if data has 'base', use it; else relative bar as approximation.
        if "base" in dff.columns:
            fig = go.Figure(
                go.Bar(
                    x=dff[x],
                    y=dff[y],
                    base=dff["base"],
                    marker=dict(color=PALETTE[0] if not color else None),
                )
            )
        else:
            fig = px.bar(dff, x=x, y=y, color=color, barmode="relative")
        fig.update_layout(barmode="relative")
    elif ctype == "horizontal_bar":
        # Для horizontal_bar: категория (регион) на Y (слева), значение на X (снизу).
        # Сортируем по убыванию значения, чтобы largest был сверху.
        # После px явно задаём categoryorder, чтобы порядок не реверсился plotly'ем.
        if color is None and len(dff) > 1:
            dff = dff.sort_values(y, ascending=False)
        fig = px.bar(dff, x=y, y=x, color=color, orientation="h")
        # Гарантируем: largest сверху (первая строка dff после desc sort -> top)
        try:
            cat_order = dff[x].tolist()
            fig.update_yaxes(categoryorder="array", categoryarray=cat_order)
        except Exception:
            pass
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
    elif ctype == "treemap":
        fig = _build_treemap(dff, spec)
    else:
        raise ValueError(f"Неизвестный chart_type: {ctype}")

    highlighted = False
    if ctype in _BAR_TYPES:
        _apply_bar_rounding(fig, ctype)
        highlighted = _apply_highlight(fig, dff, spec, ctype)

    if ctype in _AVERAGE_TYPES:
        _apply_average_line(fig, dff, spec, ctype)

    # Value labels on bars (русские числа; Br только для денежных колонок debt/accrued/paid)
    if ctype in _BAR_TYPES:
        try:
            if y in dff.columns:
                texts = [
                    format_number_ru(v, suffix="Br" if _money_suffix(y) else "") for v in dff[y]
                ]
                fig.update_traces(text=texts, textposition="outside", textfont=dict(size=9))
        except Exception:
            pass  # non-fatal

    # Общий стиль (кроме kpi — частично переопределён выше)
    if ctype != "kpi":
        fig = apply_common_style(fig, spec, chart_type=ctype)

    # Для horizontal_bar оси в фигуре swapped по смыслу (категория на Y, значение на X),
    # поэтому переопределяем titles после apply (который использует spec x/y без учёта swap).
    # + force palette[0] для single-series (избегаем чёрных/дефолтных баров),
    # + margin bump чтобы outside value labels не обрезались,
    # + кастомные тики без английских SI (B/M) через format ru.
    if ctype == "horizontal_bar":
        fig.update_layout(
            xaxis_title=get_russian_label(y),
            yaxis_title=get_russian_label(x),
        )
        # force цвет для одного ряда (если highlight не применён)
        if color is None and not highlighted:
            with suppress(Exception):
                fig.update_traces(
                    marker_color=PALETTE[0],
                    marker=dict(color=PALETTE[0], cornerradius=6),
                )
        # margin bump (справа для текста labels на x-axis horizontal bars)
        with suppress(Exception):
            fig.update_layout(margin=dict(l=200, r=140, t=80, b=120))
            fig.update_xaxes(automargin=True)
            fig.update_yaxes(automargin=True)
        # тик-форматтер на value axis (x) без "14B"
        with suppress(Exception):
            if y in dff.columns and len(dff) > 0:
                vals = [v for v in dff[y] if isinstance(v, (int, float))]
                if vals:
                    # 5 опорных тиков
                    mn, mx = min(vals), max(vals)
                    if mx > mn:
                        step = (mx - mn) / 4.0
                        tv = [mn + i * step for i in range(5)]
                    else:
                        tv = [mn]
                    tickvals = [float(v) for v in tv]
                    ticktext = make_ru_ticktext(
                        tickvals, suffix=""
                    )  # без Br на оси для чистоты, на барах есть
                    fig.update_xaxes(tickvals=tickvals, ticktext=ticktext)

        # очистка hovertemplate от сырых алиасов (total_debt= -> русское) для чистоты PNG/экспорта
        if ctype in {"bar", "grouped_bar", "stacked_bar", "horizontal_bar", "line"}:
            for trace in fig.data:
                ht = getattr(trace, "hovertemplate", None)
                if ht:
                    ht = str(ht)
                    for raw, ru in [
                        ("total_debt=", "Задолженность, Br="),
                        ("debt=", "Задолженность, Br="),
                        ("accrued=", "Начислено, Br="),
                        ("total_accrued=", "Начислено, Br="),
                        ("paid=", "Уплачено, Br="),
                    ]:
                        ht = ht.replace(raw, ru)
                    with suppress(Exception):
                        trace.hovertemplate = ht

    # Hover с русским форматом для чисел (упрощённо)
    if ctype in {"bar", "grouped_bar", "stacked_bar", "line", "horizontal_bar"}:
        for trace in fig.data:
            if hasattr(trace, "hovertemplate") and trace.hovertemplate:
                # plotly сам использует :, но мы оставляем; при необходимости post-process
                pass

    # Фиксируем размер для экспорта (kpi уже свой)
    if ctype != "kpi":
        fig.update_layout(width=CHART_WIDTH, height=CHART_HEIGHT)

    if ctype in ("bar", "horizontal_bar", "line"):
        _annotate_max_point(fig, dff, spec, ctype)

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
