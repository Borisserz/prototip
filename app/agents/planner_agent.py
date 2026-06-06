"""PlannerAgent (первая версия, Вариант A).

Простой intent-based роутер.
Принимает вопрос → определяет intent → вызывает ровно один основной агент
через AgentExecutor → возвращает его результат.

Всё происходит скрыто: пользователь не видит план, вызванные агенты
и внутренний reasoning.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.executor import AgentExecutor, AgentRegistry
from app.agents.models import AgentResult
from core.llm import call_structured, setup_logging

setup_logging()
logger = logging.getLogger("PlannerAgent")


class _Intent(BaseModel):
    """Внутренняя схема для structured classification intent'а."""

    intent: Literal[
        "chart",
        "dashboard",
        "presentation",
        "data",
        "general",
        "comparison",
        "trend",
        "summary",
    ] = Field(..., description="Какой основной тип ответа лучше всего подходит пользователю")
    refined_question: str | None = Field(
        None, description="Уточнённая формулировка вопроса, если нужно (опционально)"
    )
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Уверенность в классификации (0-1)"
    )
    reason: str = Field(
        default="", description="Краткое внутреннее обоснование выбора (не показывать пользователю)"
    )


FEW_SHOT_INTENT = """
Ты — точный и консервативный классификатор запросов для BI-платформы налоговой аналитики Республики Беларусь (синтетические данные 2024, валюта Br).

Твоя задача — определить **один** наиболее подходящий intent для ответа пользователю.

### Поддерживаемые intents:

- **chart**: Один конкретный график (столбец, линия, круговая и т.д.). 
  Примеры: "задолженность по регионам", "динамика начислений в г. Минск за год", "топ-5 регионов по НДС", "структура налогов по видам", "график уплаченного по регионам".

- **comparison**: Сравнение 2+ категорий/регионов (часто приводит к grouped/stacked bar или нескольким линиям).
  Примеры: "сравни задолженность Гомельской и Минской областей", "как отличаются начисления по подоходному налогу между регионами".

- **trend**: Динамика, изменение во времени, тренд.
  Примеры: "как менялись начисления в Брестской области за год?", "тренд задолженности по НДС".

- **dashboard**: Комплексный обзор — несколько взаимосвязанных графиков + KPI на одном экране.
  Примеры: "дашборд по задолженности по регионам", "обзор ключевых метрик налогов за 2024", "комплексный анализ поступлений".

- **presentation**: Готовая презентация (.pptx со слайдами, титульным, выводами).
  Примеры: "сделай презентацию по налогам", "подготовь отчёт-презентацию по собираемости", "презентация по динамике налогов".

- **data**: Сырые данные, таблица, выгрузка без визуализации.
  Примеры: "покажи данные по Минску", "выгрузи таблицу по НДС за январь", "данные по Брестской области".

- **summary**: Общие выводы, ключевые наблюдения, итоговый анализ без конкретного графика.
  Примеры: "какие основные выводы по налогам за год?", "что происходит со собираемостью?".

- **general**: Размытый, общий или неопределённый вопрос, не попадающий под вышеперечисленное.
  Примеры: "расскажи про налоги", "что ты умеешь?", "анализ налогов".

### Правила классификации:
- Если вопрос про **один** визуальный элемент (график, диаграмма, топ, динамику) → chart / comparison / trend.
- Если про **несколько** графиков + обзор → dashboard.
- Если явно про слайды / pptx / доклад → presentation.
- Если про "данные", "таблицу", "выгрузку" без "график" → data.
- Если про "выводы", "итоги", "что происходит" без визуала → summary.
- При неоднозначности (например "покажи что-то по задолженности") — выбирай наиболее вероятный и ставь confidence ниже 0.7.
- Всегда возвращай строго валидный JSON по схеме _Intent. Никакого текста вне JSON.

Примеры:
Q: "Какая задолженность по регионам?" → {"intent": "chart", "confidence": 0.95, "reason": "Один график топ/сравнение"}
Q: "Дашборд по начислениям и задолженности" → {"intent": "dashboard", "confidence": 0.9, "reason": "Несколько графиков + обзор"}
Q: "Сделай презентацию по налогам" → {"intent": "presentation", "confidence": 0.98, "reason": "Явно про pptx"}
Q: "Покажи данные по Гомельской области" → {"intent": "data", "confidence": 0.85, "reason": "Таблица/сырые данные"}
Q: "Какие главные выводы по собираемости?" → {"intent": "summary", "confidence": 0.8, "reason": "Итоговый анализ без визуала"}
Q: "Расскажи про налоги в Беларуси" → {"intent": "general", "confidence": 0.7, "reason": "Слишком общо"}
"""


class PlannerAgent(BaseAgent):
    """PlannerAgent (Вариант A) — простой intent-based роутер.

    Принимает вопрос пользователя, с помощью LLM определяет наиболее подходящий
    тип ответа (intent) и вызывает ровно один основной агент через AgentExecutor.

    Вся внутренняя логика (классификация, вызовы вспомогательных агентов,
    сборка результата) полностью скрыта от пользователя. Он видит только
    финальный результат (график, дашборд, презентацию или данные).
    """

    name = "planner_agent"
    description = (
        "Главный агент: анализирует вопрос пользователя и направляет его одному "
        "подходящему специалисту (график, дашборд, презентация или данные). "
        "Внутренние детали скрыты от пользователя."
    )

    def __init__(self) -> None:
        """Инициализирует реестр и исполнитель агентов.

        Регистрирует все доступные агенты один раз при создании Planner'а.
        Простое кэширование похожих запросов (in-memory, для демо).
        """
        self.registry = AgentRegistry()
        self.executor = AgentExecutor(self.registry)

        # Регистрируем доступные агенты (создаём один раз)
        from app.agents.analyst_agent import AnalystAgent
        from app.agents.chart_agent import ChartAgent
        from app.agents.dashboard_agent import DashboardAgent
        from app.agents.data_agent import DataAgent
        from app.agents.presentation_agent import PresentationAgent

        self.executor.register(DataAgent())
        self.executor.register(AnalystAgent())
        self.executor.register(ChartAgent())
        self.executor.register(DashboardAgent())
        self.executor.register(PresentationAgent())

        self._cache: dict[str, AgentResult] = {}  # простой кэш вопрос -> результат

    def _classify_intent(self, question: str) -> tuple[str, float, str | None]:
        """Определяет intent запроса с помощью LLM (structured output).

        Возвращает (intent, confidence, refined_question или None).
        При низкой уверенности или ошибке — fallback на 'general'.
        """
        try:
            prompt = f"""{FEW_SHOT_INTENT}

Вопрос пользователя: {question}

Верни только валидный JSON по схеме _Intent.
"""
            intent_obj: _Intent = call_structured(
                prompt,
                schema=_Intent,
                system="Ты — точный и консервативный классификатор. При сомнениях выбирай 'general' и низкий confidence.",
            )

            intent = intent_obj.intent
            confidence = max(0.0, min(1.0, intent_obj.confidence))
            refined = intent_obj.refined_question

            # Нормализация (Вариант A — маппим на основные)
            if intent in ("comparison", "trend", "dynamics"):
                intent = "chart"
            elif intent == "summary":
                intent = "dashboard"

            # Защита
            valid_intents = {"chart", "dashboard", "presentation", "data", "general"}
            if intent not in valid_intents:
                intent = "general"
                confidence = min(confidence, 0.5)

            logger.info(
                f"[PlannerAgent] classified intent={intent} (conf={confidence:.2f}, reason: {intent_obj.reason[:80] if intent_obj.reason else 'n/a'})"
            )
            return intent, confidence, refined

        except Exception as e:
            logger.warning(f"[PlannerAgent] classification failed: {e}. Falling back to 'general'")
            return "general", 0.3, None

    def _handle_chart_intent(self, question: str) -> AgentResult:
        """Умная и гибкая обработка запросов, требующих визуализации (chart / comparison / trend).

        Логика:
        - Всегда пытаемся получить данные через DataAgent (для свежести и безопасности).
        - Если DataAgent упал — пытаемся graceful fallback.
        - Строим ChartAgent.
        - Добавляем AnalystAgent (опционально, с защитой).
        - Собираем максимально полный AskResult для красивого рендера в чате.
        """
        from app.schemas import AnalysisResult, AskResult

        try:
            # 1. Получаем данные (почти всегда нужно для chart)
            data_res = self.executor.run("data_agent", question)

            if not getattr(data_res, "success", False):
                logger.warning(
                    f"[PlannerAgent] DataAgent failed for chart intent. Error: {getattr(data_res, 'error', 'unknown')}"
                )
                # Пытаемся отдать хотя бы то, что есть (пустой или ошибочный результат)
                if hasattr(data_res, "data") and data_res.data:
                    # Редкий случай — данные частично есть
                    pass
                else:
                    return data_res

            data = getattr(data_res, "data", []) or []
            sql = getattr(data_res, "sql", "") or ""

            if not data:
                logger.info(
                    "[PlannerAgent] No data returned for chart intent — returning data_res as-is"
                )
                return data_res

            # 2. Строим график
            chart_res = self.executor.run("chart_agent", question, data=data)
            chart_spec = (
                getattr(chart_res, "spec", None) if getattr(chart_res, "success", False) else None
            )

            if not chart_spec:
                logger.warning("[PlannerAgent] ChartAgent did not return a valid spec")
                # Fallback: возвращаем данные + сообщение
                return AskResult(
                    question=question,
                    sql=sql,
                    data=data,
                    analysis=AnalysisResult(
                        insights=["Не удалось автоматически выбрать тип графика."],
                        key_conclusion="Данные получены, но визуализация может быть неоптимальной.",
                        anomaly_or_trend=None,
                    ),
                    chart_spec=None,
                    png_path=None,
                )

            # 3. Анализ (graceful — не критично для chart)
            analysis = None
            try:
                analysis_res = self.executor.run("analyst_agent", question, data=data)
                if getattr(analysis_res, "success", False) and hasattr(analysis_res, "insights"):
                    analysis = analysis_res
            except Exception as e:
                logger.info(f"[PlannerAgent] AnalystAgent skipped gracefully for chart: {e}")

            if not analysis:
                analysis = AnalysisResult(
                    insights=["График построен на основе полученных данных."],
                    key_conclusion="Визуализация выполнена успешно.",
                    anomaly_or_trend=None,
                )

            # 4. Финальная сборка
            return AskResult(
                question=question,
                sql=sql,
                data=data,
                analysis=analysis,
                chart_spec=chart_spec,
                png_path=None,  # live render в чате
            )

        except Exception as e:
            logger.error(f"[PlannerAgent] _handle_chart_intent failed: {e}")
            return AgentResult(
                success=False,
                reasoning="Не удалось построить график. Попробуйте переформулировать вопрос или уточнить период/регион.",
                error=str(e),
            )

    def run(self, question: str) -> AgentResult:
        """Главная точка входа PlannerAgent (Вариант A).

        1. Классифицирует вопрос (с confidence).
        2. Если уверенность низкая — возвращает уточняющий вопрос (пользователь увидит текст).
        3. Иначе вызывает ровно один основной агент (с поддержкой для chart).
        4. Возвращает результат, удобный для рендера в чате.

        Пользователь **не видит** ни intent, ни вызванные агенты, ни reasoning.
        """
        logger.info(f"[PlannerAgent] start: question={question[:70]}...")

        # Простое кэширование (нормализованный ключ)
        cache_key = question.strip().lower()[:120]
        if cache_key in self._cache:
            logger.info("[PlannerAgent] cache hit")
            return self._cache[cache_key]

        intent, confidence, refined_q = self._classify_intent(question)
        q = refined_q or question

        # Простые уточняющие вопросы при низкой уверенности (Tier 2)
        if confidence < 0.55:
            clarification_text = (
                "Я не совсем понял, какой формат ответа вам нужен. "
                "Хотите один график, дашборд с несколькими графиками, презентацию или просто данные/выводы? "
                "Пожалуйста, уточните вопрос."
            )
            from app.schemas import AnalysisResult

            return AnalysisResult(
                insights=[clarification_text],
                key_conclusion="Уточните, пожалуйста, желаемый формат ответа.",
                anomaly_or_trend=None,
            )

        try:
            if intent in ("chart", "comparison", "trend"):
                result = self._handle_chart_intent(q)
            elif intent == "dashboard":
                from app.schemas import DashboardRequest

                req = DashboardRequest(question=q)
                result = self.executor.run("dashboard_agent", req)
            elif intent == "presentation":
                result = self.executor.run("presentation_agent", [q])
            elif intent == "data":
                result = self.executor.run("data_agent", q)
            else:  # general + summary
                result = self.executor.run("analyst_agent", q, data=[])

            # Дополнительная защита: если под-агент вернул ошибку, но не упал — логируем и возвращаем как есть (UI покажет)
            if not getattr(result, "success", True):
                logger.warning(f"[PlannerAgent] sub-agent returned non-success for intent={intent}")
            else:
                # Кэшируем только успешные результаты
                self._cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(
                f"[PlannerAgent] execution_error for intent={intent} (conf={confidence:.2f}): {e}"
            )
            # Самый верхний уровень — всегда возвращаем понятный результат
            return AgentResult(
                success=False,
                reasoning="Произошла ошибка при обработке запроса. Попробуйте переформулировать вопрос или уточнить, что именно нужно (график, дашборд, презентация или данные).",
                error=str(e),
            )

    def get_capabilities(self) -> dict:
        """Возвращает описание возможностей агента (для introspection и будущего Planner)."""
        return {
            "name": self.name,
            "description": self.description,
            "supported_intents": [
                "chart",
                "comparison",
                "trend",  # визуализация одного графика
                "dashboard",  # комплексный обзор (KPI + несколько графиков)
                "presentation",  # генерация .pptx
                "data",  # сырые данные / таблица
                "summary",
                "general",  # текстовый анализ / общие выводы
            ],
            "features": [
                "intent classification with confidence",
                "graceful error handling + partial results",
                "simple in-memory caching of similar queries",
                "clarifying questions on low confidence",
            ],
        }
