"""Фабрика графиков.

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

from core import storage
from core.models import ChartSpec

from .style import (
    CHART_HEIGHT,
    CHART_WIDTH,
    MUTED_BAR_COLOR,
    PALETTE,
    apply_common_style,
    compose_title_text,
    format_number_ru,
    get_russian_label,
    make_ru_ticktext,
)

_HOVER_RU_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("total_debt=", "Задолженность, Br="),
    ("debt=", "Задолженность, Br="),
    ("accrued=", "Начислено, Br="),
    ("total_accrued=", "Начислено, Br="),
    ("paid=", "Уплачено, Br="),
    ("total_paid=", "Уплачено, Br="),
    ("penalties=", "Штрафы и пени, Br="),
    ("total_penalties=", "Штрафы и пени, Br="),
)
_MAX_ANNOTATION_CATEGORIES = 12

_BAR_TYPES = frozenset({"bar", "grouped_bar", "stacked_bar", "horizontal_bar"})
_AVERAGE_TYPES = frozenset({"bar", "line", "area", "horizontal_bar"})


def _annotate_max_point(fig: go.Figure, dff: pd.DataFrame, spec: ChartSpec, ctype: str) -> None:
    """Стрелка на максимум для bar / horizontal_bar / line (говорящий график)."""
    try:
        if ctype not in ("bar", "horizontal_bar", "line"):
            return
        if len(dff) > _MAX_ANNOTATION_CATEGORIES:
            return
        if spec.show_average or spec.color is not None:
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
    return (
        any(k in str(y_col).lower() for k in ("debt", "accrued", "paid", "penalt"))
        and "taxpayer" not in str(y_col).lower()
    )


def _apply_ru_hover_templates(fig: go.Figure) -> None:
    """Заменяет сырые имена колонок в hovertemplate на русские подписи."""
    for trace in fig.data:
        ht = getattr(trace, "hovertemplate", None)
        if not ht:
            continue
        ht = str(ht)
        for raw, ru in _HOVER_RU_REPLACEMENTS:
            ht = ht.replace(raw, ru)
        with suppress(Exception):
            trace.hovertemplate = ht


def _sort_chronological_if_period(dff: pd.DataFrame, col: str) -> pd.DataFrame:
    if col not in dff.columns or col.lower() != "period":
        return dff
    try:
        return dff.sort_values(col, ascending=True)
    except Exception:
        return dff


def _apply_top_n_and_sort(dff: pd.DataFrame, spec: ChartSpec, ctype: str) -> pd.DataFrame:
    """top_n и sort_order после агрегации."""
    out = dff.copy()
    cat_col = spec.x
    val_col = spec.y

    if cat_col in out.columns and cat_col.lower() == "period":
        out = _sort_chronological_if_period(out, cat_col)
    elif spec.sort_order and spec.sort_order != "none" and val_col in out.columns:
        ascending = spec.sort_order == "asc"
        out = out.sort_values(val_col, ascending=ascending)
    elif ctype == "horizontal_bar" and val_col in out.columns and spec.color is None:
        out = out.sort_values(val_col, ascending=False)

    if spec.top_n and spec.top_n > 0 and val_col in out.columns:
        out = (
            out.nlargest(spec.top_n, val_col)
            if spec.sort_order != "asc"
            else out.nsmallest(spec.top_n, val_col)
        )
    return out


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
    highlight = getattr(spec, "highlight_category", None)
    if not highlight or spec.color is not None:
        return False
    if ctype not in _BAR_TYPES:
        return False

    cat_col = _category_col_for_highlight(spec, ctype)
    if cat_col not in dff.columns:
        return False

    target = str(highlight).strip().lower()
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
    fig = px.treemap(
        dff,
        path=path_cols,
        values=spec.y,
        color=spec.y,
        color_continuous_scale=[[0, PALETTE[1]], [0.5, PALETTE[4]], [1, PALETTE[0]]],
    )
    with suppress(Exception):
        fig.update_traces(
            texttemplate="%{label}<br>%{value:,.0f}",
            hovertemplate="<b>%{label}</b><br>%{value:,.0f}<extra></extra>",
        )
    return fig


def _build_waterfall(dff: pd.DataFrame, spec: ChartSpec) -> go.Figure:
    """Настоящий waterfall через go.Waterfall (накопительные шаги)."""
    x_col, y_col = spec.x, spec.y
    if "base" in dff.columns:
        return go.Figure(
            go.Bar(
                x=dff[x_col],
                y=dff[y_col],
                base=dff["base"],
                marker=dict(color=PALETTE[0]),
            )
        )

    measures: list[str] = []
    values: list[float] = []
    for pos, (_, row) in enumerate(dff.iterrows()):
        val = float(row[y_col])
        if pos == 0:
            measures.append("absolute")
        elif pos == len(dff) - 1 and len(dff) > 1:
            measures.append("total")
        else:
            measures.append("relative")
        values.append(val)

    if len(measures) == 1:
        measures = ["absolute"]

    text_vals = [format_number_ru(v, suffix="Br" if _money_suffix(y_col) else "") for v in values]
    return go.Figure(
        go.Waterfall(
            name=get_russian_label(y_col),
            orientation="v",
            x=[str(v) for v in dff[x_col]],
            y=values,
            measure=measures,
            text=text_vals,
            textposition="outside",
            connector=dict(line=dict(color="#CCCCCC", width=1)),
            increasing=dict(marker=dict(color=PALETTE[2])),
            decreasing=dict(marker=dict(color=PALETTE[5])),
            totals=dict(marker=dict(color=PALETTE[0])),
        )
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
    if ctype != "kpi":
        dff = _apply_top_n_and_sort(dff, spec, ctype)
        if spec.x in dff.columns:
            dff = _sort_chronological_if_period(dff, spec.x)

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
        fig = _build_waterfall(dff, spec)
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
        title_html = compose_title_text(spec)
        if "<br>" not in title_html:
            title_html = f"{title_html}<br><span style='font-size:0.6em'>{label}</span>"
        fig = go.Figure(
            go.Indicator(
                mode="number",
                value=total,
                number={
                    "valueformat": ",",
                    "font": {"size": 68, "color": PALETTE[0]},
                    "prefix": "",
                },
                title={"text": title_html},
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

    if ctype in {"bar", "grouped_bar", "stacked_bar", "line", "horizontal_bar", "area"}:
        _apply_ru_hover_templates(fig)

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
    # зеркалим PNG в MinIO (неломающе; при отключённом MinIO — no-op)
    storage.mirror_artifact(p, "charts")
    return p


def export_html(fig: go.Figure, path: str | Path, include_plotlyjs: str = "cdn") -> Path:
    """Экспорт интерактивного HTML."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(p), include_plotlyjs=include_plotlyjs, full_html=True)
    # зеркалим HTML в MinIO (неломающе)
    storage.mirror_artifact(p, "charts")
    return p
