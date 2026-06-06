"""Тесты единого стиля (viz/style.py).

Проверяют форматтер чисел (пробел), лейблы, apply (обновляет layout + annotation).
"""

from __future__ import annotations

import plotly.graph_objects as go

from viz.style import (
    PALETTE,
    apply_common_style,
    compose_title_text,
    format_number_ru,
    get_russian_label,
)


class _DummySpec:
    """Минимальный объект для теста apply (как ChartSpec)."""

    def __init__(self, **kwargs: object) -> None:
        self.title = "Тестовый график"
        self.subtitle = "Проверка стиля"
        self.x = "region"
        self.y = "accrued"
        self.source = "Синтетические данные: тесты"
        self.action_title = None
        self.chart_type = "bar"
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_format_number_ru_spaces_and_suffix() -> None:
    """Пробел как thousands sep + суффикс Br, компакт для больших (млрд/млн)."""
    assert format_number_ru(1234567) == "1 234 567 Br"
    assert format_number_ru(1234567.89, decimals=2, suffix="Br") == "1 234 567.89 Br"
    assert format_number_ru(42) == "42 Br"
    # компакт (только для очень больших)
    assert format_number_ru(14_200_000_000) == "14,2 млрд Br"
    assert format_number_ru(1_234_000_000) == "1,2 млрд Br"
    assert format_number_ru(56_000_000) == "56 млн Br"
    assert format_number_ru(5_600_000) == "5 600 000 Br"  # не компакт
    # с total_debt fallback в label (отдельный тест)


def test_get_russian_label_dataset_cols() -> None:
    """Маппинг колонок датасета на русский. Устойчив к total_debt / sum_ и т.п."""
    assert get_russian_label("accrued") == "Начислено, Br"
    assert get_russian_label("region") == "Регион"
    assert get_russian_label("period") == "Месяц"
    assert get_russian_label("taxpayers") == "Число налогоплательщиков"
    assert get_russian_label("debt") == "Задолженность, Br"
    assert get_russian_label("total_debt") == "Задолженность, Br"
    assert get_russian_label("sum_debt") == "Задолженность, Br"
    assert get_russian_label("debt_total") == "Задолженность, Br"
    assert get_russian_label("total_accrued") == "Начислено, Br"
    assert get_russian_label("foo_bar") == "Foo Bar"  # fallback cleaned (no English leak)
    # анти-english даже в fallback
    # "debt" слово может остаться в fallback для weird, но фраза Total Debt не должна
    assert get_russian_label("weird_total_debt_col") != "Total Debt"
    assert get_russian_label("total_debt") != "Total Debt"


def test_palette_has_eight_colorblind_colors() -> None:
    """Ровно 8 цветов Okabe-Ito."""
    assert len(PALETTE) == 8
    assert all(c.startswith("#") and len(c) == 7 for c in PALETTE)


def test_compose_title_text_with_action_title() -> None:
    spec = _DummySpec(
        action_title="г. Минск доминирует в начислениях",
        title="Начисления по регионам",
        subtitle="2024 год",
    )
    text = compose_title_text(spec)
    assert "г. Минск доминирует" in text
    assert "Начисления по регионам" in text
    assert "2024 год" in text


def test_apply_common_style_updates_layout_and_footer() -> None:
    """apply добавляет title, font, colorway, footer annotation."""
    fig = go.Figure(go.Bar(x=["a", "b"], y=[1_200_000, 3_400_000]))
    spec = _DummySpec()
    styled = apply_common_style(fig, spec, chart_type="bar")

    assert styled.layout.title.text is not None
    assert styled.layout.hoverlabel.bgcolor == "white"
    assert styled.layout.yaxis.showgrid is True
    assert styled.layout.xaxis.showgrid is False
    assert "Тестовый график" in str(styled.layout.title.text)
    assert styled.layout.font.family == "Arial, sans-serif"
    assert styled.layout.colorway is not None
    assert styled.layout.colorway[0] == PALETTE[0]
    assert len(styled.layout.colorway) == len(PALETTE)

    # Footer annotation присутствует
    ann_texts = [a.text for a in (styled.layout.annotations or [])]
    assert any("Синтетические данные" in (t or "") for t in ann_texts)
