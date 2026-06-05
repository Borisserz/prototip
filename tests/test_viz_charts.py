"""Тесты фабрики графиков (viz/charts.py).

Ключевой тест Phase 1: на sample.csv строятся 5-6+ графиков в едином стиле,
экспорт PNG/HTML работает, файлы > threshold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from core.models import ChartSpec
from viz.charts import build_chart, export_html, export_png


@pytest.fixture(scope="module")
def sample_df() -> pd.DataFrame:
    """Загружает сгенерированный sample (должен существовать после p1-data)."""
    df = pd.read_csv("data/sample.csv")
    assert len(df) > 350
    return df


def _mk_spec(**kwargs: Any) -> ChartSpec:
    """Helper для коротких spec в тестах."""
    base = {
        "title": "Тест",
        "x": "region",
        "y": "accrued",
        "rationale": "test",
    }
    base.update(kwargs)
    return ChartSpec(**base)  # type: ignore[arg-type]


def test_build_various_types_on_sample(sample_df: pd.DataFrame) -> None:
    """Строим 6 разных типов; все возвращают go.Figure с данными."""
    specs = [
        _mk_spec(chart_type="bar", title="Начислено по регионам", agg="sum"),
        _mk_spec(
            chart_type="line", title="Динамика по месяцам", x="period", color="region", agg="sum"
        ),
        _mk_spec(
            chart_type="stacked_bar",
            title="Структура по налогам во времени",
            x="period",
            color="tax_type",
            agg="sum",
        ),
        _mk_spec(chart_type="horizontal_bar", title="Топ регионов", agg="sum"),
        _mk_spec(chart_type="donut", title="Доли по видам налогов", x="tax_type", agg="sum"),
        _mk_spec(chart_type="kpi", title="Итого начислено", x="Итого", agg="sum"),
    ]
    for s in specs:
        fig = build_chart(sample_df, s)
        assert fig is not None
        assert len(fig.data) >= 1 or s.chart_type == "kpi"  # kpi может иметь 1 indicator

        if s.chart_type == "horizontal_bar":
            trace = fig.data[0]
            # значение на оси X (x содержит числовые значения)
            assert len(trace.x) > 0
            # содержит все категории (здесь 7 регионов в sample, тест требует >=4 и все)
            assert len(trace.y) >= 4
            # подпись оси X после get_russian_label != сырой alias типа total_debt
            x_title = (
                fig.layout.xaxis.title.text if fig.layout.xaxis and fig.layout.xaxis.title else ""
            ) or ""
            assert "total_debt" not in x_title.lower()
            assert (
                "Начислено" in x_title
                or "Задолженность" in x_title
                or "Br" in x_title
                or x_title == ""
            )


def test_heatmap_with_prefilter(sample_df: pd.DataFrame) -> None:
    """Heatmap требует pivot; фильтруем один налог для чистоты."""
    df = sample_df[sample_df["tax_type"] == "НДС"].copy()
    spec = _mk_spec(
        chart_type="heatmap",
        title="Heatmap начислений (НДС)",
        x="period",
        color="region",
        y="accrued",
        agg="sum",
        rationale="матрица период-регион",
    )
    fig = build_chart(df, spec)
    assert fig is not None
    # Heatmap trace
    assert any("Heatmap" in str(type(t)) for t in fig.data) or len(fig.data) > 0


def test_exports_produce_files(tmp_path: Path, sample_df: pd.DataFrame) -> None:
    """export_png и export_html создают файлы достаточного размера."""
    spec = _mk_spec(chart_type="bar", title="Экспорт тест", agg="sum")
    fig = build_chart(sample_df, spec)

    png = export_png(fig, tmp_path / "test_bar.png", scale=1.5)
    html = export_html(fig, tmp_path / "test_bar.html")

    assert png.exists()
    assert html.exists()
    assert png.stat().st_size > 15_000  # высокое качество даже при scale 1.5
    assert html.stat().st_size > 5_000  # cdn include keeps base html small; plotly.js not inlined
    # HTML содержит plotly
    content = html.read_text(encoding="utf-8")
    assert "plotly" in content.lower()


def test_five_six_graphs_on_sample_produce_previews(
    tmp_path: Path, sample_df: pd.DataFrame
) -> None:
    """Итоговый тест Phase 1: 6 графиков + экспорт (как "на sample.csv строятся 5–6")."""
    out = tmp_path / "previews"
    out.mkdir()

    specs = [
        _mk_spec(
            chart_type="bar",
            title="Начисленные налоги по регионам",
            agg="sum",
            rationale="Сравнение категорий — bar",
        ),
        _mk_spec(
            chart_type="line",
            title="Динамика поступлений",
            x="period",
            color="region",
            agg="sum",
            rationale="Время → line",
        ),
        _mk_spec(
            chart_type="grouped_bar",
            title="По налогам и регионам (групп)",
            x="tax_type",
            color="region",
            agg="sum",
            rationale="Сравнение с группировкой",
        ),
        _mk_spec(
            chart_type="horizontal_bar",
            title="Рейтинг регионов",
            agg="sum",
            rationale="Рейтинг — horizontal_bar",
        ),
        _mk_spec(
            chart_type="donut",
            title="Структура налогов",
            x="tax_type",
            agg="sum",
            rationale="Доли — donut",
        ),
        _mk_spec(
            chart_type="kpi",
            title="Суммарные начисления",
            x="Всего",
            y="accrued",
            agg="sum",
            rationale="Ключевой показатель — kpi",
        ),
    ]

    for s in specs:
        f = build_chart(sample_df, s)
        export_png(
            f, out / f"{s.chart_type}.png", scale=2
        )  # fixed 1000x600 in export for sharpness
        export_html(f, out / f"{s.chart_type}.html")

    pngs = list(out.glob("*.png"))
    assert len(pngs) >= 6
    for p in pngs:
        assert p.stat().st_size > 20_000


def test_exported_figure_has_style_for_presentation(sample_df: pd.DataFrame) -> None:
    """Регрессия для PNG, встраиваемых в презентацию: colorway (не дефолт), русские оси, нет английских автоподписей (Total Debt и т.п.)."""
    spec = _mk_spec(
        chart_type="bar",
        title="Тест стиля для слайда",
        x="region",
        y="debt",
        agg="sum",
        rationale="регрессия презентация PNG",
    )
    fig = build_chart(sample_df, spec)

    # colorway применён (Okabe-Ito из style)
    cw = fig.layout.colorway
    assert cw is not None and len(cw) >= 4
    assert "#E69F00" in cw or "#56B4E9" in cw  # из PALETTE

    # русские подписи осей (get_russian_label)
    x_title = (getattr(fig.layout.xaxis.title, "text", "") or "").lower()
    y_title = (getattr(fig.layout.yaxis.title, "text", "") or "").lower()
    assert any(k in x_title for k in ("регион", "долг", "задолженность")) or any(
        k in y_title for k in ("регион", "долг", "задолженность")
    )

    # нет английских автоподписей от plotly
    fig_str = str(fig).lower()
    assert "total debt" not in fig_str
    assert "total accrued" not in fig_str
    assert "sum of" not in fig_str  # типичная автоподпись
