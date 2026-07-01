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
# Базовый результат агента (самое важное для  и Planner)
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
    trace: PlannerTrace | None = Field(
        None,
        description="Трассировка PlannerAgent (план, шаги, agent_calls)",
    )
    confidence_score: float = Field(
        1.0, ge=0.0, le=1.0, description="Уровень уверенности агента в результате (0.0 - 1.0)"
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Список рекомендаций от агента для следующих шагов (CrewAI Flow pattern)",
    )


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
    correlation_id: str | None = Field(None, description="Сквозной ID запроса")


class PlanExecutionStep(BaseModel):
    """Один шаг выполнения плана PlannerAgent (для UI trace)."""

    num: int
    agent_name: str
    description: str
    status: str
    brief_result: str = ""
    depends_on: list[str] = Field(default_factory=list)


class PlannerTrace(BaseModel):
    """Трассировка выполнения PlannerAgent: план, шаги, вызовы агентов."""

    executed_plan: Plan | None = None
    plan_execution: list[PlanExecutionStep] = Field(default_factory=list)
    agent_calls: list[AgentCall] = Field(default_factory=list)


# =============================================================================
# Результаты DataAgent
# =============================================================================


class DrilldownContext(BaseModel):
    """Структурный контекст детализация из UI (фильтры с графика)."""

    filters: dict[str, str] = Field(
        default_factory=dict,
        description="Активные фильтры: region, tax_type, period",
    )
    dimension: str = Field(default="_segment", description="Основное измерение детализация")
    segment_label: str = Field(default="", description="Человекочитаемая метка сегмента")
    trail: list[dict[str, str]] = Field(
        default_factory=list,
        description="Цепочка предыдущих шагов детализации",
    )


class DataAgentInput(BaseModel):
    """Вход для DataAgent (вопрос на русском)."""

    question: str = Field(..., min_length=5, description="Вопрос пользователя на русском")
    drilldown_filters: dict[str, str] | None = Field(
        None,
        description="Жёсткие фильтры из детализация UI (region/tax_type/period)",
    )


class SqlResult(AgentResult):
    """Результат DataAgent: SQL + данные (для /5)."""

    step_by_step_planning: str = Field(
        ...,
        description="Пошаговый план: 1. Какие таблицы нужны 2. Какие фильтры 3. Какая группировка (CoT)",
    )
    sql: str = Field(..., description="Корректный исполняемый SELECT (только чтение)")
    data: list[dict] = Field(..., description="Результат в виде списка записей (records)")
    row_count: int = Field(..., description="Число строк в результате")


# =============================================================================
# Результаты AnalystAgent
# =============================================================================


class AnalysisResult(AgentResult):
    """Результат AnalystAgent: структурированные инсайты на русском."""

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
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="2-3 логичных уточняющих вопроса для дальнейшего анализа",
    )
    data_explanation: str | None = Field(
        None,
        description="Простое объяснение: как получены цифры (фильтры, группировка, агрегация)",
    )
    degraded: bool = Field(
        False,
        description="True если анализ получен из резервный вариант, а не от LLM",
    )


# =============================================================================
# Результаты ChartAgent
# =============================================================================


class ChartAgentInput(BaseModel):
    """Вход для ChartAgent (вопрос + данные для выбора типа и заполнения spec)."""

    question: str = Field(..., description="Оригинальный вопрос на русском")
    data: list[dict] = Field(..., description="Данные (records) из DataAgent или запроса")


class ChartAgentResult(AgentResult):
    """Выход ChartAgent: готовая спецификация."""

    specs: list[ChartSpec] = Field(default_factory=list)


# =============================================================================
# Результаты RagAgent
# =============================================================================


class RagResult(AgentResult):
    """Результат RagAgent: найденный текстовый контекст и источники."""

    context: str = Field(..., description="Найденный и объединённый текст из базы знаний")
    sources: list[str] = Field(
        default_factory=list, description="Список источников (документов/страниц)"
    )
    source_snippets: list[dict] = Field(
        default_factory=list, description="Расширенные метаданные со сниппетами"
    )


# =============================================================================
# Результаты Orchestrator (ask)
# =============================================================================


class AskResult(AgentResult):
    """Полный результат одного вопроса (Orchestrator )."""

    question: str
    sql: str = ""
    data: list[dict] = Field(default_factory=list)
    analysis: AnalysisResult | None = None
    chart_spec: ChartSpec | None = None  # первичный ChartSpec от chart_agent (slide pipeline)
    charts: list[ChartSpec] = Field(default_factory=list)
    rag_result: RagResult | None = None
    png_path: str | None = None  # путь к артефакту в out/
    excel_path: str | None = None
    pptx_path: str | None = None


# =============================================================================
# Презентации
# =============================================================================


class SupervisorDecision(BaseModel):
    """Решение Supervisory Node."""

    route: Literal["data", "direct_answer"] = Field(
        ...,
        description="Маршрут выполнения: 'data' (если нужен SQL) или 'direct_answer' (если просто текст)",
    )
    direct_response: str | None = Field(None, description="Ответ, если route == direct_answer")


class SlideData(BaseModel):
    """Данные одного слайда для отображения и редактирования в UI."""

    slide_idx: int
    slide_type: str = Field(
        description="'title', 'summary', 'themes', 'chart', 'takeaways', 'recommendations', 'appendix'"
    )
    title: str
    content: str | list[str] | None = None


class SlideUpdate(BaseModel):
    """Частичное обновление данных слайда."""

    title: str | None = None
    content: str | list[str] | None = None
    chart_type: str | None = None  # e.g. 'bar', 'line', 'donut', 'pie', 'horizontal_bar'


class PresentationUpdateRequest(BaseModel):
    """полезная нагрузка для POST /api/v1/presentation/update."""

    presentation_id: str
    slide_updates: dict[int, SlideUpdate]


class PresentationInput(BaseModel):
    """Вход для PresentationAgent."""

    questions: list[str] = Field(
        ..., min_length=1, description="Список вопросов на русском для сборки презентации"
    )


class PresentationResult(AgentResult):
    """Результат PresentationAgent: путь к .pptx и метаданные."""

    pptx_path: str = Field(
        ..., description="Путь к созданному файлу презентации (out/presentation.pptx)"
    )
    excel_path: str | None = Field(
        default=None, description="Путь к сгенерированному Excel-файлу (если запрашивался)."
    )
    num_slides: int = Field(..., description="Количество слайдов в презентации")
    slide_png_paths: list[str] = Field(
        default_factory=list,
        description="Пути к PNG-превью слайдов с графиками (out/pres_slide_*.png)",
    )
    presentation_id: str = Field(
        default="",
        description="Уникальный id прогона для изоляции PNG-превью",
    )
    slides: list[SlideData] = Field(
        default_factory=list, description="Текстовое содержимое слайдов для редактирования в UI"
    )


class PresentationState(BaseModel):
    """Сохраненное состояние для перегенерации презентации без LLM."""

    presentation_id: str
    questions: list[str]
    prefs: dict[int, str | None]
    results: list[AskResult]
    narrative: DeckNarrative
    include_title: bool
    include_recommendations: bool
    num_slides: int | None


class DeckNarrative(AgentResult):
    """Структурированный нарратив для презентации."""

    overview: str = Field(
        ...,
        description="Детальный обзор: цель, охват (период, регионы, виды налогов, объёмы в млрд бел. руб.), метод, ключевые числа и аномалии",
    )
    themes: list[str] = Field(..., description="5-7 ключевых тем/разделов с конкретными числами")
    key_takeaways: list[str] = Field(
        ..., description="7-10 детальных выводов с цифрами, %, сравнениями"
    )
    recommendations: list[str] = Field(
        ..., description="4-6 конкретных рекомендаций с КПЭ и ожидаемым эффектом"
    )


class QuestionBlock(BaseModel):
    """Один блок вопроса из формы UI."""

    text: str = Field(..., min_length=5)
    chart_type: str | None = Field(
        None, description="Предпочтительный тип: авто/line/bar/donut/horizontal_bar"
    )
    note: str | None = None


class PresentationRequest(BaseModel):
    """полезная нагрузка для POST /generate_presentation (от UI формы)."""

    mode: str = Field(..., description="По вопросам | Свободная тема | Одним предложением")
    overall_theme: str | None = Field(None)
    questions: list[QuestionBlock] = Field(default_factory=list)
    num_slides: int = Field(10, ge=3, le=30)
    include_title: bool = True
    include_recommendations: bool = True
    audience: str | None = Field(None, description="executive | analyst | board")
    detail_level: str | None = Field(None, description="standard | detailed | comprehensive")


# =============================================================================
# Дашборды (DashboardAgent)
# =============================================================================


class KpiCard(BaseModel):
    """KPI-карточка для верхней части дашборда."""

    name: str = Field(..., description="Название метрики на русском, напр. 'Общая задолженность'")
    value: float | str = Field(..., description="Значение: число или уже отформатированная строка")
    unit: str = Field("", description="Единица измерения, напр. 'бел. руб.', '%', 'регионов'")
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
    drilldown_filters: dict[str, str] | None = Field(
        None,
        description="Жёсткие фильтры детализация для вложенного DataAgent",
    )


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
    recommendations: list[str] = Field(
        default_factory=list,
        description="2-4 практические бизнес-рекомендации на основе данных",
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


AgentResult.model_rebuild()


class LoginRequest(BaseModel):
    username: str
    password: str


class ClientLoginRequest(BaseModel):
    """Вход заказчика по API-ключу или личному JWT-токену."""

    api_key: str | None = None
    token: str | None = None
