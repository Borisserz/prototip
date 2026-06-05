"""Pydantic контракты для агентов (Phase 2+).

Все данные между агентами/оркестратором — только через эти модели (никаких dict).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.models import ChartSpec


class DataAgentInput(BaseModel):
    """Вход для DataAgent (вопрос на русском)."""

    question: str = Field(..., min_length=5, description="Вопрос пользователя на русском")


class SqlResult(BaseModel):
    """Результат DataAgent: SQL + данные (для Phase 2/5)."""

    sql: str = Field(..., description="Корректный исполняемый SELECT (только чтение)")
    data: list[dict] = Field(..., description="Результат в виде списка записей (records)")
    row_count: int = Field(..., description="Число строк в результате")


class ChartAgentInput(BaseModel):
    """Вход для ChartAgent (вопрос + данные для выбора типа и заполнения spec)."""

    question: str = Field(..., description="Оригинальный вопрос на русском")
    data: list[dict] = Field(..., description="Данные (records) из DataAgent или запроса")


class ChartAgentResult(BaseModel):
    """Выход ChartAgent: готовая спецификация (Phase 4)."""

    spec: ChartSpec


class AnalysisResult(BaseModel):
    """Результат AnalystAgent (Phase 3): структурированные инсайты на русском."""

    insights: list[str] = Field(
        ...,
        min_length=3,
        max_length=4,
        description="3-4 чётких инсайта/тезиса на русском (тренды, аномалии, топы, сравнения)",
    )
    key_conclusion: str = Field(..., description="Ключевой вывод (одно-два предложения, без воды)")
    anomaly_or_trend: str | None = Field(
        None, description="Замеченная аномалия или тренд (если выявлена)"
    )


class AskResult(BaseModel):
    """Полный результат одного вопроса (Orchestrator Phase 5)."""

    question: str
    sql: str
    data: list[dict]
    analysis: AnalysisResult | None = None
    chart_spec: ChartSpec | None = None
    png_path: str | None = None  # путь к артефакту в out/


class PresentationInput(BaseModel):
    """Вход для PresentationAgent (Phase 6)."""

    questions: list[str] = Field(
        ..., min_length=1, description="Список вопросов на русском для сборки презентации"
    )


class PresentationResult(BaseModel):
    """Результат PresentationAgent: путь к .pptx и метаданные."""

    pptx_path: str = Field(
        ..., description="Путь к созданному файлу презентации (out/presentation.pptx)"
    )
    num_slides: int = Field(..., description="Количество слайдов в презентации")


class DeckNarrative(BaseModel):
    """Структурированный нарратив для презентации (Phase 8+)."""

    overview: str = Field(
        ...,
        description="Обзор: цель презентации, охват (период, регионы, виды налогов, объёмы), метод (локальная мультиагентная система Text-to-SQL + анализ + визуализация)",
    )
    themes: list[str] = Field(
        ..., min_length=2, max_length=4, description="2-4 ключевые темы/повестки дня"
    )
    key_takeaways: list[str] = Field(
        ..., min_length=4, max_length=6, description="4-6 главных выводов по всей колоде"
    )
    recommendations: list[str] = Field(
        ..., min_length=2, max_length=4, description="2-4 конкретные рекомендации"
    )


class QuestionBlock(BaseModel):
    """Один блок вопроса из формы UI."""

    text: str = Field(..., min_length=5)
    chart_type: str | None = Field(
        None, description="Предпочтительный тип: авто/line/bar/donut/horizontal_bar"
    )
    note: str | None = None


class PresentationRequest(BaseModel):
    """Payload для POST /generate_presentation (от UI формы)."""

    mode: str = Field(..., description="По вопросам | Свободная тема | Одним предложением")
    overall_theme: str | None = Field(None)
    questions: list[QuestionBlock] = Field(default_factory=list)
    num_slides: int = Field(5, ge=3, le=12)
    include_title: bool = True
    include_recommendations: bool = True
    # для изображений/CSV в будущем можно добавить base64 или пути, но для Phase тонкий


# === Dashboard (Phase next sprint) ===
# Контракты для DashboardAgent: комплексный дашборд из нескольких ChartSpec + KPI + insights.
# Следует spec-first: LLM возвращает спецификации, рендер — детерминированный viz/.
# Все тексты на русском. Переиспользуем ChartSpec из core (не дублируем).
# data + source_sql добавлены для рендера в UI (build_chart) и отладки без повторных дорогостоящих вызовов.


class KpiCard(BaseModel):
    """KPI-карточка для верхней части дашборда."""

    name: str = Field(..., description="Название метрики на русском, напр. 'Общая задолженность'")
    value: float | str = Field(..., description="Значение: число или уже отформатированная строка")
    unit: str = Field("", description="Единица измерения, напр. 'Br', '%', 'регионов'")
    change: float | None = Field(
        None, description="Относительное изменение в % (положительное — рост)"
    )
    change_period: str | None = Field(
        None, description="Период изменения, напр. 'к предыдущему месяцу'"
    )


class DashboardLayout(BaseModel):
    """Рекомендация по расположению элементов дашборда (для будущего UI/рендера)."""

    type: Literal["kpi_top_grid", "two_column", "tabs", "single_column"] = Field(
        "kpi_top_grid", description="Тип лейаута"
    )
    columns: int = Field(2, ge=1, le=4, description="Число колонок для графиков")


class DashboardRequest(BaseModel):
    """Вход для DashboardAgent."""

    question: str = Field(
        ...,
        min_length=5,
        description="Естественный вопрос пользователя на русском, напр. 'Дашборд по задолженности по регионам'",
    )
    data: list[dict] | None = Field(
        None,
        description="Опциональные данные (records). Если None — агент самостоятельно вызовет DataAgent для получения.",
    )
    max_charts: int = Field(4, ge=1, le=6, description="Максимальное число графиков в дашборде")
    include_kpi: bool = Field(True, description="Включать ли KPI-карточки")


class DashboardResult(BaseModel):
    """Выход DashboardAgent: полный структурированный дашборд."""

    title: str = Field(..., description="Заголовок дашборда на русском")
    summary: str = Field(..., description="Краткое саммари (2-4 предложения)")
    kpi_cards: list[KpiCard] = Field(
        default_factory=list, description="KPI-карточки (если запрошены)"
    )
    charts: list[ChartSpec] = Field(
        default_factory=list,
        description="Список спецификаций графиков (3-5 шт.). Рендер через viz/charts.py",
    )
    layout: DashboardLayout = Field(
        default_factory=DashboardLayout, description="Рекомендуемый layout"
    )
    insights: list[str] = Field(
        default_factory=list,
        description="3-6 аналитических инсайтов на русском (высокоуровневые по всему дашборду)",
    )
    data: list[dict] = Field(
        default_factory=list,
        description="Данные (records) использованные для построения дашборда (для рендера графиков в UI без перезапроса LLM/DataAgent)",
    )
    source_sql: str | None = Field(
        None,
        description="SQL запрос (если известен), использованный для получения данных (для отладки/экспорта)",
    )
    generated_at: datetime = Field(default_factory=datetime.now)
    reasoning: str = Field(
        ..., description="Обоснование выбора графиков, layout, KPI (для отладки и прозрачности)"
    )
