"""Детерминированные KPI для обзорных слайдов (дашборд / презентация)."""

from __future__ import annotations

import pandas as pd

from viz.style import format_number_ru


def compute_overview_kpis(data: list[dict]) -> list[tuple[str, str]]:
    """Возвращает до 4 пар (название, значение) из сырых records."""
    if not data:
        return []
    try:
        df = pd.DataFrame(data)
        cards: list[tuple[str, str]] = []
        if "accrued" in df.columns:
            cards.append(
                ("Суммарные начисления", format_number_ru(float(df["accrued"].sum()), suffix="бел. руб."))
            )
        if "debt" in df.columns:
            cards.append(
                ("Общая задолженность", format_number_ru(float(df["debt"].sum()), suffix="бел. руб."))
            )
        if "region" in df.columns:
            cards.append(("Регионов в выборке", str(int(df["region"].nunique()))))
        if "tax_type" in df.columns:
            cards.append(("Видов налогов", str(int(df["tax_type"].nunique()))))
        return cards[:4]
    except Exception:
        return []