"""Unified Pydantic models for agents (preparation for PlannerAgent).

Все контракты между агентами — только через эти модели (никаких голых dict).
AgentResult — базовый класс результата для всех агентов (с success/reasoning/error).

Сюда перенесены основные модели результатов/входов агентов из app/schemas.py и core
для унификации (агенты импортируют отсюда; schemas.py ре-экспортирует для API/UI).

ChartSpec остаётся в core/models.py (контракт viz/, не дублируем).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.models import ChartSpec  # re-export for convenience inside agents package

# =============================================================================
# Базовый результат агента (самое важное для Phase 2+ и Planner)
# =============================================================================


class AgentResult(BaseModel):
    """Базовый результат любого агента.

    Все агенты (через BaseAgent.run) должны возвращать модель, унаследованную от AgentResult
    (или напрямую AgentResult для простых случаев). Поле reasoning обязательно для
    наблюдаемости и будущего PlannerAgent.
    """

    success: bool = Field(True, description="Успешно ли выполнился агент")
    reasoning: str = Field(
        default="",
        description="Обоснование принятых решений, наблюдения по данным, почему выбран такой результат (для отладки и Planner)",
    )
    error: str | None = Field(None, description="Текст ошибки, если success=False")


# =============================================================================
# Модели для будущего PlannerAgent (Task / Plan / AgentCall)
# =============================================================================


class Task(BaseModel):
    """Единица работы в иерархическом плане (PlannerAgent).

    Planner будет разбивать пользовательский вопрос на Tasks, назначать agent_name,
    указывать зависимости и параметры.
    """

    id: str = Field(..., description="Уникальный идентификатор задачи в плане")
    description: str = Field(..., description="Человекочитаемое описание подзадачи (на русском)")
    agent_name: str = Field(
        ..., description="Имя агента, который должен выполнить задачу (data/analyst/chart/...)"
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="Параметры для вызова агента (question, filters и т.д.)"
    )
    depends_on: list[str] = Field(
        default_factory=list, description="Список id задач, которые должны выполниться до этой"
    )
    priority: int = Field(0, description="Приоритет (меньше = раньше)")


class Plan(BaseModel):
    """Полный план выполнения запроса пользователя.

    Состоит из списка Task. PlannerAgent будет генерировать Plan, Orchestrator/Executor — исполнять.
    """

    goal: str = Field(
        ..., description="Итоговая цель пользователя (оригинальный вопрос или сформулированная)"
    )
    tasks: list[Task] = Field(default_factory=list, description="Последовательность/граф задач")
    strategy: str = Field(
        default="",
        description="Краткое описание стратегии (почему именно такой набор задач и порядок)",
    )
    estimated_steps: int | None = Field(None, description="Оценочное число шагов")


class AgentCall(BaseModel):
    """Запись одного вызова агента (для трассировки, логов, кэша, Planner)."""

    agent_name: str
    input_summary: str = Field("", description="Краткое описание входа (для лога)")
    success: bool = True
    duration_ms: int | None = None
    reasoning: str = ""
    error: str | None = None
    output_summary: str = Field("", description="Краткое описание результата")


# =============================================================================
# Результаты DataAgent
# =============================================================================


class DataAgentInput(BaseModel):
    """Вход для DataAgent (вопрос на русском)."""

    question: str = Field(..., min_length=5, description="Вопрос пользователя на русском")


class SqlResult(AgentResult):
    """Результат DataAgent: SQL + данные (для Phase 2/5)."""

    sql: str = Field(..., description="Корректный исполняемый SELECT (только чтение)")
    data: list[dict] = Field(..., description="Результат в виде списка записей (records)")
    row_count: int = Field(..., description="Число строк в результате")


# =============================================================================
# Результаты AnalystAgent
# =============================================================================


class AnalysisResult(AgentResult):
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


# =============================================================================
# Результаты ChartAgent
# =============================================================================


class ChartAgentInput(BaseModel):
    """Вход для ChartAgent (вопрос + данные для выбора типа и заполнения spec)."""

    question: str = Field(..., description="Оригинальный вопрос на русском")
    data: list[dict] = Field(..., description="Данные (records) из DataAgent или запроса")


class ChartAgentResult(AgentResult):
    """Выход ChartAgent: готовая спецификация (Phase 4)."""

    spec: ChartSpec


# =============================================================================
# Результаты Orchestrator (ask)
# =============================================================================


class AskResult(AgentResult):
    """Полный результат одного вопроса (Orchestrator Phase 5)."""

    question: str
    sql: str = ""
    data: list[dict] = Field(default_factory=list)
    analysis: AnalysisResult | None = None
    chart_spec: ChartSpec | None = None
    png_path: str | None = None  # путь к артефакту в out/


# =============================================================================
# Презентации
# =============================================================================


class PresentationInput(BaseModel):
    """Вход для PresentationAgent (Phase 6)."""

    questions: list[str] = Field(
        ..., min_length=1, description="Список вопросов на русском для сборки презентации"
    )


class PresentationResult(AgentResult):
    """Результат PresentationAgent: путь к .pptx и метаданные."""

    pptx_path: str = Field(
        ..., description="Путь к созданному файлу презентации (out/presentation.pptx)"
    )
    num_slides: int = Field(..., description="Количество слайдов в презентации")


class DeckNarrative(AgentResult):
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


# =============================================================================
# Дашборды (DashboardAgent)
# =============================================================================


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


class DashboardResult(AgentResult):
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
    # reasoning унаследован от AgentResult; DashboardAgent всегда заполняет его явно
