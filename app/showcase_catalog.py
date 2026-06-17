"""Каталог спецификаций для демо-портфолио (showcase/) — графики и презентации."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from core.models import ChartSpec

SOURCE = "Синтетические данные (демо), Республика Беларусь"


@dataclass(frozen=True)
class ChartShowcaseEntry:
    """Один элемент галереи графиков."""

    index: int
    slug: str
    spec: ChartSpec
    filter_tax_type: str | None = None
    use_waterfall_df: bool = False


@dataclass(frozen=True)
class PresentationBundle:
    """Набор вопросов для одной executive-презентации."""

    filename: str
    title: str
    questions: list[dict[str, Any]]
    num_slides: int
    overview: str
    themes: list[str]
    key_takeaways: list[str]
    recommendations: list[str]


def waterfall_demo_df() -> pd.DataFrame:
    """Детерминированные шаги для водопадной диаграммы."""
    return pd.DataFrame(
        {
            "step": [
                "Начисления",
                "Уплачено",
                "Штрафы",
                "Остаток долга",
            ],
            "change": [142_000_000_000.0, -98_000_000_000.0, 8_500_000_000.0, 52_500_000_000.0],
        }
    )


def chart_showcase_entries() -> list[ChartShowcaseEntry]:
    """12 кураторских ChartSpec — по одному на каждый поддерживаемый тип."""
    return [
        ChartShowcaseEntry(
            1,
            "bar",
            ChartSpec(
                chart_type="bar",
                title="Начисленные налоги по регионам",
                subtitle="Сумма начислений за 2024 год, бел. руб.",
                x="region",
                y="accrued",
                agg="sum",
                action_title="г. Минск — лидер по объёму начислений",
                show_average=True,
                insights=[
                    "г. Минск концентрирует наибольший объём начислений",
                    "Восточные области показывают стабильный рост",
                    "Подоходный налог — ключевой драйвер в регионах",
                ],
                rationale="Сравнение категорий — столбчатая диаграмма",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            2,
            "grouped_bar",
            ChartSpec(
                chart_type="grouped_bar",
                title="Начисления по видам налогов и регионам",
                x="tax_type",
                y="accrued",
                color="region",
                agg="sum",
                action_title="НДС и подоходный налог доминируют в г. Минске",
                insights=[
                    "НДС — крупнейший вид налога в большинстве регионов",
                    "г. Минск опережает области по всем основным видам",
                    "Акцизы — наименьшая доля в структуре",
                ],
                rationale="Сравнение с группировкой — grouped_bar",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            3,
            "stacked_bar",
            ChartSpec(
                chart_type="stacked_bar",
                title="Структура начислений по месяцам",
                x="period",
                y="accrued",
                color="tax_type",
                agg="sum",
                sort_order="asc",
                action_title="Доля НДС в структуре растёт к концу года",
                insights=[
                    "Сезонный рост начислений в Q4",
                    "НДС формирует основу стека",
                    "Имущественные налоги стабильны по месяцам",
                ],
                rationale="Структура во времени — stacked_bar",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            4,
            "line",
            ChartSpec(
                chart_type="line",
                title="Динамика задолженности по регионам",
                x="period",
                y="debt",
                color="region",
                agg="sum",
                sort_order="asc",
                action_title="Задолженность растёт к концу 2024 года",
                insights=[
                    "Общий восходящий тренд по всем регионам",
                    "Гомельская и Могилёвская области — выше среднего",
                    "г. Минск демонстрирует умеренную динамику",
                ],
                rationale="Время + несколько серий — line",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            5,
            "area",
            ChartSpec(
                chart_type="area",
                title="Накопительная динамика штрафов и пеней",
                x="period",
                y="penalties",
                color="region",
                agg="sum",
                sort_order="asc",
                action_title="Накопление штрафов ускоряется во II полугодии",
                insights=[
                    "Штрафы растут быстрее в восточных областях",
                    "Пик приходится на осенние месяцы",
                    "Корреляция с уровнем задолженности",
                ],
                rationale="Накопительная динамика — area",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            6,
            "scatter",
            ChartSpec(
                chart_type="scatter",
                title="Корреляция начислений и задолженности",
                x="accrued",
                y="debt",
                color="region",
                agg="none",
                action_title="Высокие начисления не всегда означают высокий долг",
                insights=[
                    "Положительная корреляция с разбросом по регионам",
                    "Выбросы требуют отдельного анализа",
                    "г. Минск — наибольшая плотность наблюдений",
                ],
                rationale="Распределение и корреляция — scatter",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            7,
            "waterfall",
            ChartSpec(
                chart_type="waterfall",
                title="Водопад формирования задолженности",
                x="step",
                y="change",
                agg="none",
                action_title="Начисления → уплата → штрафы → остаток долга",
                insights=[
                    "Уплата существенно снижает начисленный объём",
                    "Штрафы добавляют вторичную нагрузку",
                    "Итоговый остаток — зона контроля",
                ],
                rationale="Водопад изменений — waterfall",
                source=SOURCE,
            ),
            use_waterfall_df=True,
        ),
        ChartShowcaseEntry(
            8,
            "horizontal_bar",
            ChartSpec(
                chart_type="horizontal_bar",
                title="Рейтинг регионов по задолженности",
                x="region",
                y="debt",
                agg="sum",
                top_n=7,
                sort_order="desc",
                show_average=True,
                highlight_category="Гомельская область",
                action_title="Гомельская область — лидер по задолженности",
                insights=[
                    "Восточные области лидируют по абсолютному долгу",
                    "Разрыв между лидером и аутсайдером превышает 2:1",
                    "Средний уровень превышен в 4 регионах",
                ],
                rationale="Рейтинг — horizontal_bar",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            9,
            "donut",
            ChartSpec(
                chart_type="donut",
                title="Структура начислений по видам налогов",
                x="tax_type",
                y="accrued",
                agg="sum",
                action_title="НДС — крупнейшая доля в структуре начислений",
                insights=[
                    "НДС — основной источник поступлений",
                    "Подоходный налог — второй по значимости",
                    "Акцизы — меньшая, но стабильная доля",
                ],
                rationale="Доли — donut",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            10,
            "kpi",
            ChartSpec(
                chart_type="kpi",
                title="Совокупная задолженность",
                x="Итого",
                y="debt",
                agg="sum",
                action_title="Совокупная задолженность превышает 15 млрд бел. руб.",
                insights=[
                    "Ключевой показатель для мониторинга собираемости",
                    "Требует ежемесячного контроля",
                    "Связан с динамикой начислений и уплат",
                ],
                rationale="Один ключевой показатель — kpi",
                source=SOURCE,
            ),
        ),
        ChartShowcaseEntry(
            11,
            "heatmap",
            ChartSpec(
                chart_type="heatmap",
                title="Тепловая карта начислений: регион × месяц (НДС)",
                x="period",
                y="accrued",
                color="region",
                agg="sum",
                sort_order="asc",
                action_title="Пик начислений НДС — в конце года в г. Минске",
                insights=[
                    "Концентрация в г. Минск и Минской области",
                    "Сезонность выражена в Q4",
                    "Слабые значения в отдельных областях",
                ],
                rationale="Матрица период-регион — heatmap",
                source=SOURCE,
                filter_tax_type="НДС",
            ),
        ),
        ChartShowcaseEntry(
            12,
            "treemap",
            ChartSpec(
                chart_type="treemap",
                title="Иерархия начислений: регион → вид налога",
                x="region",
                y="accrued",
                color="tax_type",
                agg="sum",
                action_title="г. Минск доминирует в общем объёме начислений",
                insights=[
                    "г. Минск — крупнейший сегмент",
                    "НДС — доминирующий вид внутри регионов",
                    "Структура неоднородна по областям",
                ],
                rationale="Иерархия >4 категорий — treemap",
                source=SOURCE,
            ),
        ),
    ]


def presentation_bundles() -> list[PresentationBundle]:
    """4 executive-набора для презентаций."""
    return [
        PresentationBundle(
            filename="01_obzor_nalogov_RB.pptx",
            title="Обзор налоговой аналитики РБ",
            num_slides=7,
            questions=[
                {"text": "Покажи сводку по начислениям по всем регионам", "chart_type": "bar"},
                {
                    "text": "Топ-3 региона по задолженности",
                    "chart_type": "horizontal_bar",
                },
                {"text": "Структура налогов по видам (доли)", "chart_type": "donut"},
            ],
            overview=(
                "Презентация содержит обзор налоговых поступлений и задолженности "
                "по синтетическим данным Республики Беларусь за 2024 год. "
                "Использована локальная мультиагентная система (Text-to-SQL + анализ + визуализация)."
            ),
            themes=[
                "Динамика начислений и задолженности по регионам",
                "Структура налогов по видам",
                "Рейтинг регионов по ключевым показателям",
            ],
            key_takeaways=[
                "г. Минск обеспечивает значительную долю начислений.",
                "Задолженность сконцентрирована в восточных областях.",
                "НДС — доминирующий вид налога в структуре.",
                "Наблюдается сезонный рост к концу года.",
            ],
            recommendations=[
                "Усилить мониторинг регионов с высокой задолженностью.",
                "Проанализировать динамику НДС по кварталам.",
            ],
        ),
        PresentationBundle(
            filename="02_reiting_zadolzhennosti.pptx",
            title="Рейтинг задолженности по регионам",
            num_slides=7,
            questions=[
                {
                    "text": "Какая задолженность по регионам — рейтинг",
                    "chart_type": "horizontal_bar",
                },
                {
                    "text": "Сравни задолженность Гомельской и Минской областей",
                    "chart_type": "bar",
                },
                {
                    "text": "Топ регионов по штрафам и пеням",
                    "chart_type": "horizontal_bar",
                    "y": "penalties",
                    "title": "Рейтинг регионов по штрафам и пеням",
                    "action_title": "Гомельская область — лидер по штрафам и пеням",
                },
            ],
            overview=(
                "Аналитический обзор задолженности, штрафов и пеней по регионам РБ. "
                "Акцент на рейтинговых диаграммах и табличных сводках для руководства."
            ),
            themes=[
                "Абсолютная задолженность по областям",
                "Штрафы и пени как индикатор риска",
                "Сравнение лидеров и аутсайдеров",
            ],
            key_takeaways=[
                "Гомельская область лидирует по задолженности.",
                "Штрафы коррелируют с уровнем долга.",
                "г. Минск — относительно низкая задолженность на душу.",
                "Требуется точечный контроль восточных регионов.",
            ],
            recommendations=[
                "Внедрить ежемесячный рейтинг задолженности по областям.",
                "Выделить пилотный регион для углублённого аудита.",
            ],
        ),
        PresentationBundle(
            filename="03_dinamika_i_struktura.pptx",
            title="Динамика и сезонность 2024",
            num_slides=8,
            questions=[
                {
                    "text": "Динамика начислений по месяцам по регионам",
                    "chart_type": "line",
                },
                {
                    "text": "Накопительная динамика штрафов по регионам",
                    "chart_type": "area",
                },
                {
                    "text": "Водопад изменений: начисления, уплата, остаток долга",
                    "chart_type": "waterfall",
                },
            ],
            overview=(
                "Временной анализ налоговых показателей за 2024 год: тренды, сезонность, "
                "накопительная динамика штрафов и водопад формирования задолженности."
            ),
            themes=[
                "Месячная динамика начислений",
                "Сезонные пики и спады",
                "Структурные изменения задолженности",
            ],
            key_takeaways=[
                "Сезонный рост начислений в Q4.",
                "Штрафы нарастают во втором полугодии.",
                "Уплата существенно снижает начисленный объём.",
                "Тренд задолженности — умеренно положительный.",
            ],
            recommendations=[
                "Скорректировать прогнозы с учётом сезонности Q4.",
                "Усилить контроль уплат в преддверии отчётных периодов.",
            ],
        ),
        PresentationBundle(
            filename="04_kompleksny_analiticheskiy.pptx",
            title="Комплексный аналитический отчёт",
            num_slides=10,
            questions=[
                {
                    "text": "Структура начислений по регионам и видам налогов",
                    "chart_type": "treemap",
                },
                {
                    "text": "Тепловая карта начислений НДС по регионам и месяцам",
                    "chart_type": "heatmap",
                },
                {
                    "text": "Корреляция начислений и задолженности по регионам",
                    "chart_type": "scatter",
                },
                {
                    "text": "Начисления по налогам и регионам — группированная диаграмма",
                    "chart_type": "grouped_bar",
                },
            ],
            overview=(
                "Комплексный аналитический отчёт: иерархия, матрицы, корреляции и сравнительный "
                "анализ по всем ключевым измерениям демо-датасета налогов РБ."
            ),
            themes=[
                "Иерархическая структура начислений",
                "Матричный анализ НДС",
                "Корреляции и сравнения",
                "Мультиагентная аналитика",
            ],
            key_takeaways=[
                "г. Минск доминирует в иерархии начислений.",
                "НДС концентрируется в столичном регионе.",
                "Корреляция начислений и долга не линейна.",
                "Группированный анализ выявляет региональные различия.",
                "Система поддерживает 12 типов визуализации.",
            ],
            recommendations=[
                "Расширить дашборд тепловыми картами по всем видам налогов.",
                "Внедрить регулярные scatter-анализы для выявления аномалий.",
                "Использовать treemap для презентаций структуры руководству.",
            ],
        ),
    ]