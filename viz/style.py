"""Единая дизайн-система для всех графиков (viz/charts.py).

Профессиональная палитра (цветовая слепота), русское форматирование чисел (пробел),
шрифты, заголовки/подписи источника, общий apply.
НИКОГДА не хардкодь цвета/шрифты вне этого модуля.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

# Okabe-Ito (colorblind-safe, 8 цветов, профессиональный)
PALETTE: list[str] = [
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
    "#000000",  # black
]

FONT_FAMILY: str = "Arial, sans-serif"
CHART_WIDTH: int = 1000
CHART_HEIGHT: int = 600
MARGINS: dict[str, int] = {"l": 70, "r": 40, "t": 115, "b": 105}


def format_number_ru(value: float | int, decimals: int = 0, suffix: str = "Br") -> str:
    """Форматирует число с пробелом как разделителем тысяч + единица Br (русский стандарт).

    Для больших значений использует компакт: "14,2 млрд Br", "1 234 млн Br".
    Убирает английские SI (B/M/k). Всегда русский стиль.
    Пример: 14200000000 -> "14,2 млрд Br"
    """
    v = float(value)
    abs_v = abs(v)
    if abs_v >= 1_000_000_000:
        compact = v / 1_000_000_000
        s = f"{compact:,.1f}".replace(",", " ").replace(".0", "").replace(".", ",") + " млрд"
    elif abs_v >= 10_000_000:
        compact = v / 1_000_000
        s = f"{compact:,.1f}".replace(",", " ").replace(".0", "").replace(".", ",") + " млн"
    else:
        s = f"{int(round(v)):,}" if decimals == 0 else f"{v:,.{decimals}f}"
        s = s.replace(",", " ")
    if suffix:
        s = f"{s} {suffix}"
    return s


def get_russian_label(col: str) -> str:
    """Русские подписи для осей/легенды по колонкам датасета + fallback.
    Устойчиво к агрегированным именам (total_debt, sum_debt, debt_total и т.п.).
    В fallback всегда используем нормализованный c (не сырой col с английским title()).
    """
    if not col:
        return ""
    c = str(col).lower().strip()
    # нормализация вариантов алиасов (включая reverse total_debt etc)
    c = (
        c.replace("total_debt", "debt")
        .replace("debt_total", "debt")
        .replace("sum_debt", "debt")
        .replace("totaldebt", "debt")
        .replace("total_accrued", "accrued")
        .replace("sum_accrued", "accrued")
        .replace("total_paid", "paid")
        .replace("sum_paid", "paid")
    )
    # префикс-стрип для оставшихся агг
    for prefix in ("total_", "sum_", "avg_", "mean_", "count_"):
        if c.startswith(prefix):
            c = c[len(prefix) :]
            break
    mapping = {
        "period": "Месяц",
        "region": "Регион",
        "tax_type": "Вид налога",
        "accrued": "Начислено, Br",
        "paid": "Уплачено, Br",
        "debt": "Задолженность, Br",
        "taxpayers": "Число налогоплательщиков",
        "value": "Значение",
    }
    if c in mapping:
        return mapping[c]
    # fallback: используем нормализованный c, не оригинальный col (предотвращает "Total Debt")
    cleaned = c.replace("_", " ").title()
    # анти-english last resort
    cl = cleaned.lower()
    if "total debt" in cl or "debt total" in cl or cl.strip() == "debt":
        return "Задолженность, Br"
    if "total accrued" in cl or "accrued total" in cl:
        return "Начислено, Br"
    if "total paid" in cl or "paid total" in cl:
        return "Уплачено, Br"
    return cleaned


def add_source_footer(fig: go.Figure, text: str) -> go.Figure:
    """Добавляет подпись источника внизу (фирменный стиль)."""
    fig.add_annotation(
        text=text,
        xref="paper",
        yref="paper",
        x=0.5,
        y=-0.18,
        showarrow=False,
        font=dict(family=FONT_FAMILY, size=10, color="#666666"),
        align="center",
    )
    return fig


def apply_common_style(fig: go.Figure, spec: Any) -> go.Figure:
    """Применяет единый стиль ко всем графикам.

    Использует PALETTE, FONT, format_number_ru, русские лейблы, footer источника.
    Вызывается внутри build_chart после создания traces.
    """
    # Title + subtitle
    title_text = spec.title
    if getattr(spec, "subtitle", None):
        title_text = f"{spec.title}<br><sub>{spec.subtitle}</sub>"

    fig.update_layout(
        title=dict(
            text=title_text,
            font=dict(family=FONT_FAMILY, size=18, color="#222222"),
            x=0.05,
            xanchor="left",
        ),
        font=dict(family=FONT_FAMILY, size=12),
        colorway=PALETTE,
        margin=MARGINS,
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        hovermode="closest",
        plot_bgcolor="#FAFAFA",
        paper_bgcolor="white",
    )

    # Оси: русские названия + subtle grid + форматирование больших чисел
    x_label = get_russian_label(getattr(spec, "x", ""))
    y_label = get_russian_label(getattr(spec, "y", ""))

    fig.update_xaxes(
        title=dict(text=x_label, font=dict(family=FONT_FAMILY, size=12)),
        gridcolor="#E8E8E8",
        linecolor="#CCCCCC",
    )
    fig.update_yaxes(
        title=dict(text=y_label, font=dict(family=FONT_FAMILY, size=12)),
        gridcolor="#E8E8E8",
        linecolor="#CCCCCC",
    )

    # Форматирование тиков Y для денег (если большие значения)
    # Простая эвристика: если max > 1e6 — форматируем
    try:
        for trace in fig.data:
            if hasattr(trace, "y") and trace.y is not None:
                yvals = [v for v in trace.y if isinstance(v, (int, float))]
                if yvals and max(yvals) > 1_000_000:
                    # Установим tickvals/ticktext (упрощённо, plotly сам форматирует hover)
                    pass  # детальный в конкретных build; здесь общий стиль
    except Exception:
        pass

    # Источник
    src = getattr(spec, "source", "Синтетические данные (демо), Республика Беларусь")
    fig = add_source_footer(fig, src)

    # Легенда под графиком (чтобы не налезала на заголовок)
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.2,
            xanchor="left",
            x=0,
            font=dict(family=FONT_FAMILY, size=10),
        )
    )

    return fig


def make_ru_ticktext(tickvals: list[float | int], suffix: str = "Br") -> list[str]:
    """Возвращает отформатированные ticktext в русском компактном стиле (без SI B/M).
    Использовать с tickvals=... для осей, чтобы избежать "14B" в PNG/фигурах.
    """
    return [format_number_ru(v, suffix=suffix) for v in tickvals]
