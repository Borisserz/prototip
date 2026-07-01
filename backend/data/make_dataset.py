"""Генератор синтетического датасета налоговых поступлений.

Реалистичные данные по регионам Республики Беларусь, видам налогов за 2024 год (демо).
Валюта — Br (белорусский рубль).
Запуск: python data/make_dataset.py
Выход: data/sample.csv (коммитится, ~500 строк).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def generate_sample_data(seed: int = 42) -> pd.DataFrame:
    """Генерирует синтетический DataFrame с колонками по PROJECT_SPEC.

    period, region, tax_type, accrued, paid, debt, taxpayers.
    Фиксированный seed для воспроизводимости.
    Добавлены аномалии для интересных графиков.
    Регионы — Республика Беларусь (7), валюта Br (демо).
    """
    rng = np.random.default_rng(seed)

    periods = [f"2024-{m:02d}" for m in range(1, 13)]
    regions = [
        "г. Минск",
        "Минская область",
        "Брестская область",
        "Витебская область",
        "Гомельская область",
        "Гродненская область",
        "Могилёвская область",
    ]
    tax_types = [
        "НДС",
        "Подоходный налог",
        "Налог на прибыль",
        "Имущественные налоги",
        "Акцизы",
    ]

    # Региональные множители (г. Минск выше)
    region_factors = {
        "г. Минск": 2.8,
        "Минская область": 1.3,
        "Брестская область": 1.0,
        "Витебская область": 0.85,
        "Гомельская область": 0.95,
        "Гродненская область": 0.9,
        "Могилёвская область": 0.8,
    }

    rows: list[dict] = []
    for period in periods:
        month = int(period.split("-")[1])
        # Сезонность: Q4 выше для НДС/прибыль
        seasonal = 1.25 if month in (10, 11, 12) else (1.1 if month in (3, 6, 9) else 1.0)

        for region in regions:
            rfactor = region_factors[region]
            for tax in tax_types:
                # Базовое начисление (демо в млн Br; г. Минск доминирует)
                base = rng.integers(4e7, 6e8) * rfactor * seasonal
                # Небольшой шум +12%
                noise = rng.normal(0, 0.12)
                accrued = max(5e6, round(base * (1 + noise), 0))

                # Уплата 65-92%
                paid_ratio = rng.uniform(0.65, 0.92)
                paid = round(accrued * paid_ratio, 0)
                debt = max(0.0, accrued - paid)

                # Налогоплательщики (демо)
                tp_base = rng.integers(8_000, 420_000)
                taxpayers = int(tp_base * (rfactor**0.35) * rng.uniform(0.9, 1.1))

                # Dataset richness: добавляем penalties (штрафы/пени) как новую колонку
                penalties = round(debt * rng.uniform(0.05, 0.18), 0)  # 5-18% от долга

                rows.append(
                    {
                        "period": period,
                        "region": region,
                        "tax_type": tax,
                        "accrued": float(accrued),
                        "paid": float(paid),
                        "debt": float(debt),
                        "taxpayers": taxpayers,
                        "penalties": float(penalties),
                    }
                )

    df = pd.DataFrame(rows)

    # Добавить аномалию: всплеск в одном регионе/налоге/месяце (Беларусь)
    mask = (
        (df["region"] == "Гомельская область")
        & (df["tax_type"] == "НДС")
        & (df["period"] == "2024-09")
    )
    df.loc[mask, "accrued"] *= 1.42
    df.loc[mask, "paid"] = df.loc[mask, "accrued"] * 0.78
    df.loc[mask, "debt"] = df.loc[mask, "accrued"] - df.loc[mask, "paid"]

    # Округлить после модификаций
    df["accrued"] = df["accrued"].round(0)
    df["paid"] = df["paid"].round(0)
    df["debt"] = df["debt"].round(0)

    df = df.sort_values(["period", "region", "tax_type"]).reset_index(drop=True)
    return df


def main() -> None:
    """Генерирует и сохраняет data/sample.csv. Печатает саммари."""
    out_path = Path("data/sample.csv")
    df = generate_sample_data(seed=42)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")

    print(f"Готово {len(df)} строк → {out_path}")
    print("Колонки:", list(df.columns))
    print(
        "Периоды:",
        df["period"].nunique(),
        "Регионы:",
        df["region"].nunique(),
        "Налоги:",
        df["tax_type"].nunique(),
    )
    print("Сумма accrued (млн Br):", round(df["accrued"].sum() / 1e6, 1))
    print("\nПервые 3 строки:")
    print(df.head(3).to_string(index=False))
    print("\nПример аномалии (Гомельская область НДС 2024-09):")
    print(
        df[
            (df["region"] == "Гомельская область")
            & (df["tax_type"] == "НДС")
            & (df["period"] == "2024-09")
        ][["accrued", "paid", "debt"]].to_string(index=False)
    )


if __name__ == "__main__":
    main()
