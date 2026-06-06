"""PlannerAgent (первая версия, Вариант A).

Простой intent-based роутер.
Принимает вопрос → определяет intent → вызывает ровно один основной агент
через AgentExecutor → возвращает его результат.

Всё происходит скрыто: пользователь не видит план, вызванные агенты
и внутренний reasoning.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.executor import AgentExecutor, AgentRegistry
from app.agents.models import (
    AgentCall,
    AgentResult,
    DashboardRequest,
    Plan,
    Task,
)
from core.llm import call_structured, setup_logging

setup_logging()
logger = logging.getLogger("PlannerAgent")

PLAN_GENERATION_PROMPT = """Ты — эксперт-планировщик для локальной мультиагентной BI-платформы налоговой аналитики Республики Беларусь (синтетические данные 2024 года, валюта Br).

Пользователь задал вопрос: {question}

Твоя задача — создать **минимально необходимый** план из **1, 2 или максимум 3 задач**, используя только эти агенты:

Доступные агенты и их сильные стороны (используй это при выборе):
- **data_agent**: только получение сырых данных (SQL + записи). params: {"question": "<вопрос для генерации SQL>"}. Нужен почти всегда как подготовительный шаг, если дальше будет chart_agent или analyst_agent.
- **chart_agent**: построение **ровно одного** графика (line, horizontal_bar, donut и т.д.). Требует данные (они придут автоматически по depends_on от data_agent). params: {"question": "<конкретный под-вопрос для этого одного графика>"}. Используй только когда пользователь явно хочет "один график", "динамику", "топ", "сравнение двух категорий".
- **analyst_agent**: генерация 3-4 текстовых инсайтов/выводов на русском. Требует данные. params: {"question": "<вопрос>"}. Используй, когда нужен именно текстовый анализ без визуализации.
- **dashboard_agent**: построение **комплексного дашборда** (KPI-карточки + 3-5 взаимосвязанных графиков + layout + summary). Сам внутри вызывает data/chart/analyst. **Предпочитай его**, когда пользователю нужен "обзор", "дашборд", "ключевые метрики", "сравнение нескольких показателей сразу". params: {"question": "<оригинальный вопрос>"} (опционально data, max_charts).
- **presentation_agent**: сборка готовой .pptx-презентации (титульный слайд + слайды с графиками + выводы + рекомендации). Принимает один вопрос или список. **Предпочитай его**, когда пользователь просит "презентацию", "отчёт", "слайды", "доклад". params: {"question": "<тема>"} или {"questions": ["q1", "q2", ...]}.

**Жёсткие правила минимизации (соблюдай в порядке приоритета):**

1. Если запрос можно полностью закрыть одной задачей — делай ровно 1 задачу.
   - Широкий обзор / несколько показателей / "дашборд" / "что происходит" → dashboard_agent.
   - Презентация / отчёт / "сделай слайды" → presentation_agent.
2. Используй цепочку data_agent → chart_agent только когда пользователь явно хочет **один конкретный график** (динамика одной серии, топ-N, один donut и т.д.).
3. Никогда не делай 3 задачи, если можно обойтись 1 или 2.
4. dashboard_agent и presentation_agent уже содержат внутри умную логику (они сами вызывают data/chart/analyst при необходимости). Не дублируй их работу.
5. depends_on указывай только когда следующая задача реально использует результат предыдущей (например chart_agent зависит от data_agent). Для dashboard_agent и presentation_agent зависимости почти никогда не нужны.

**Примеры хороших планов (минимальных и правильных):**

Вопрос: "Какая задолженность по регионам?"
→ План: 1 задача → dashboard_agent
  (даст топ, структуру, динамику, KPI — всё в одном месте)

Вопрос: "Построй график динамики начислений в г. Минск за год"
→ План: 2 задачи → data_agent → chart_agent
  (нужен именно один график линии)

Вопрос: "Сделай презентацию по денежному состоянию граждан"
→ План: 1 задача → presentation_agent
  (она сама разберёт вопрос на несколько слайдов)

**Примеры плохих планов (избегай):**

- 3 задачи (data → chart → analyst), когда достаточно одного dashboard_agent.
- Использовать chart_agent для широкого обзора (chart_agent делает только один график).
- Делать dashboard_agent + presentation_agent вместе без необходимости.
- Добавлять лишние зависимости.

После генерации плана всегда проверяй:
- Можно ли было решить вопрос меньшим количеством задач?
- Использован ли самый подходящий высокоуровневый агент?

Верни **строго** валидный JSON по схеме _PlanSpec. Не добавляй никакого текста вне JSON.
"""


class _TaskSpec(BaseModel):
    """Схема для одной задачи, которую генерирует LLM."""

    id: str = Field(..., description="Уникальный id задачи, напр. 't1', 't2'")
    description: str = Field(..., description="Короткое описание на русском, что делает эта задача")
    agent_name: str = Field(
        ...,
        description="Имя агента: data_agent, chart_agent, analyst_agent, dashboard_agent или presentation_agent",
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="Параметры для вызова агента (question, filters и т.д.)"
    )
    depends_on: list[str] = Field(
        default_factory=list, description="Список id задач, которые должны выполниться до этой"
    )


class _PlanSpec(BaseModel):
    """Схема плана, которую возвращает LLM."""

    goal: str = Field(..., description="Итоговая цель пользователя")
    tasks: list[_TaskSpec] = Field(..., max_length=3, description="Список задач (максимум 3)")
    strategy: str = Field(default="", description="Краткое описание стратегии плана")


class PlannerAgent(BaseAgent):
    """PlannerAgent v2.5 — иерархический планировщик с акцентом на качество планов.

    Ключевые улучшения генерации планов:
    - Сильный промпт с приоритетами (предпочитать dashboard/presentation для широких запросов).
    - Много хороших/плохих примеров + жёсткие правила минимизации.
    - Автоматическая валидация + оценка качества плана.
    - Self-correction (LLM получает список проблем и предлагает исправленный минимальный план).

    Пользователь видит только финальный результат + свёрнутый экспандер
    "Что было сделано" с подробной информацией по каждому шагу.
    """

    name = "planner_agent"
    description = (
        "Главный агент (v2): строит план из 1-3 задач, выполняет его с учётом зависимостей "
        "и контекста, возвращает результат. Внутренняя работа скрыта от пользователя."
    )

    def __init__(self) -> None:
        self.registry = AgentRegistry()
        self.executor = AgentExecutor(self.registry)

        # Регистрируем агенты
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

        self._cache: dict[str, AgentResult] = {}

    def _validate_plan(self, plan: Plan) -> list[str]:
        """Проверяет план на корректность. Возвращает список ошибок (пустой = план валиден)."""
        errors: list[str] = []
        known_agents = {
            "data_agent",
            "chart_agent",
            "analyst_agent",
            "dashboard_agent",
            "presentation_agent",
        }
        task_ids = {t.id for t in plan.tasks}

        for t in plan.tasks:
            if t.agent_name not in known_agents:
                errors.append(f"Задача {t.id}: неизвестный агент '{t.agent_name}'")

            for dep in t.depends_on:
                if dep not in task_ids:
                    errors.append(f"Задача {t.id}: зависимость '{dep}' не существует в плане")
                elif dep == t.id:
                    errors.append(f"Задача {t.id}: не может зависеть сама от себя")

        # Проверка порядка (зависимости должны быть раньше)
        id_to_index = {t.id: i for i, t in enumerate(plan.tasks)}
        for t in plan.tasks:
            for dep in t.depends_on:
                if id_to_index.get(dep, -1) >= id_to_index.get(t.id, -1):
                    errors.append(f"Задача {t.id}: зависимость '{dep}' должна быть раньше в плане")

        return errors

    def _assess_plan_quality(self, plan: Plan, question: str, errors: list[str]) -> float:
        """Простая эвристическая оценка качества плана (0.0 — 1.0).
        Используется для принятия решения о self-correction.
        """
        if not plan.tasks:
            return 0.0

        score = 1.0

        # Штраф за ошибки валидации
        if errors:
            score -= min(0.5, 0.15 * len(errors))

        # Штраф за слишком большое количество задач (для большинства вопросов 1-2 достаточно)
        if len(plan.tasks) >= 3:
            score -= 0.25
        elif len(plan.tasks) == 2:
            score -= 0.05

        # Бонус за использование высокоуровневых агентов для широких запросов
        high_level = {"dashboard_agent", "presentation_agent"}
        if any(t.agent_name in high_level for t in plan.tasks):
            # Если вопрос выглядит "обзорным" — это хорошо
            broad_keywords = [
                "дашборд",
                "обзор",
                "презентация",
                "отчёт",
                "состояние",
                "общее",
                "ключевые",
            ]
            if any(kw in question.lower() for kw in broad_keywords):
                score += 0.15

        # Штраф, если для обзорного вопроса использовали низкоуровневую цепочку
        low_level_chain = {"data_agent", "chart_agent", "analyst_agent"}
        if (
            len(plan.tasks) >= 2
            and all(t.agent_name in low_level_chain for t in plan.tasks)
            and any(
                kw in question.lower()
                for kw in ["дашборд", "презентация", "обзор", "состояние граждан"]
            )
        ):
            score -= 0.20

        # Бонус за наличие стратегии
        if plan.strategy and len(plan.strategy) > 15:
            score += 0.05

        return max(0.0, min(1.0, score))

    def _generate_plan(self, question: str) -> Plan:
        """
        Генерирует качественный и максимально минимальный план (1-3 задачи).

        Улучшения v2.5:
        - Очень сильный промпт с приоритетами (предпочитать dashboard/presentation).
        - Много примеров хороших vs плохих планов.
        - Жёсткие правила минимизации.
        - Автоматическая валидация + оценка качества.
        - Self-correction при ошибках или низком качестве.

        Возвращает уже провалидированный (и при необходимости исправленный) Plan.
        """
        prompt = PLAN_GENERATION_PROMPT.format(question=question)

        try:
            plan_spec: _PlanSpec = call_structured(
                prompt,
                schema=_PlanSpec,
                system="Ты — точный и консервативный планировщик. Всегда минимизируй количество задач. Отвечай только валидным JSON по схеме.",
            )

            tasks = []
            for t in plan_spec.tasks[:3]:
                tasks.append(
                    Task(
                        id=t.id,
                        description=t.description,
                        agent_name=t.agent_name,
                        params=t.params,
                        depends_on=t.depends_on,
                    )
                )

            plan = Plan(
                goal=plan_spec.goal or question,
                tasks=tasks,
                strategy=plan_spec.strategy or "Пошаговый анализ запроса",
            )

            # Валидация + оценка качества
            errors = self._validate_plan(plan)
            quality_score = self._assess_plan_quality(plan, question, errors)

            if errors or quality_score < 0.65:
                logger.info(
                    f"[PlannerAgent] plan needs correction (errors={len(errors)}, quality={quality_score:.2f}). Running self-correction..."
                )

                # Улучшенный self-correction промпт
                correction_prompt = f"""Оригинальный вопрос пользователя: {question}

Сгенерированный план:
{plan.model_dump_json(indent=2)}

Проблемы, которые нужно исправить:
{chr(10).join("- " + e for e in errors) if errors else "- План можно сделать существенно короче и лучше"}

Правила, которые ты должен был соблюсти:
- Минимум задач (предпочитать dashboard_agent или presentation_agent для широких запросов)
- Не дублировать работу высокоуровневых агентов
- Использовать правильные зависимости

Создай **исправленную и максимально минимальную** версию этого плана. Верни только _PlanSpec.
"""
                try:
                    corrected_spec: _PlanSpec = call_structured(
                        correction_prompt,
                        schema=_PlanSpec,
                        system="Ты — строгий рецензент планов. Исправляй на минимальные и правильные планы. Только валидный JSON.",
                    )

                    # Пересобираем план
                    tasks = []
                    for t in corrected_spec.tasks[:3]:
                        tasks.append(
                            Task(
                                id=t.id,
                                description=t.description,
                                agent_name=t.agent_name,
                                params=t.params,
                                depends_on=t.depends_on,
                            )
                        )
                    plan = Plan(
                        goal=corrected_spec.goal or question,
                        tasks=tasks,
                        strategy=corrected_spec.strategy or "Исправленный минимальный план",
                    )

                    # Повторная валидация после коррекции
                    errors = self._validate_plan(plan)
                    quality_score = self._assess_plan_quality(plan, question, errors)
                    logger.info(
                        f"[PlannerAgent] self-correction done. New quality score: {quality_score:.2f}"
                    )

                except Exception as corr_e:
                    logger.warning(
                        f"[PlannerAgent] self-correction failed: {corr_e}. Keeping current plan."
                    )

            logger.info(
                f"[PlannerAgent] final plan: {len(plan.tasks)} tasks, quality≈{quality_score:.2f}, strategy: {plan.strategy}"
            )
            return plan

        except Exception as e:
            logger.warning(f"[PlannerAgent] plan generation failed: {e}. Using safe fallback.")
            return Plan(
                goal=question,
                tasks=[
                    Task(
                        id="t1",
                        description="Построить комплексный дашборд по запросу пользователя",
                        agent_name="dashboard_agent",
                        params={"question": question},
                    )
                ],
                strategy="Fallback: прямой вызов dashboard_agent (самый надёжный для большинства вопросов)",
            )

    def _invoke_agent(
        self, agent_name: str, params: dict[str, Any], original_question: str
    ) -> AgentResult:
        """Подготавливает правильные аргументы и вызывает агент через executor.

        Это центральное место, которое знает сигнатуры run() всех агентов:
        - data_agent: run(question: str)
        - chart_agent / analyst_agent: run(question: str, data: list[dict])  (используем **call_kwargs)
        - dashboard_agent: run(request: DashboardRequest)
        - presentation_agent: run(questions: list[str] | PresentationInput | ...)

        Всегда очищаем "result_from_*" junk из контекста. Используем executor.run
        так же, как это делает Orchestrator (str + data=kw для низкоуровневых).
        """
        p = {k: v for k, v in (params or {}).items() if not str(k).startswith("result_from_")}
        q = str(p.get("question") or p.get("q") or original_question or "").strip()

        if agent_name == "data_agent":
            # DataAgent.run принимает bare str (внутри делает DataAgentInput)
            arg = q or original_question
            return self.executor.run(agent_name, arg)

        if agent_name in ("chart_agent", "analyst_agent"):
            # Эти два требуют (question, data). Orchestrator уже делает так:
            # executor.run("chart_agent", question, data=...)
            # executor пробросит data= как kwarg → agent.run(q, data=the_list)
            data = p.get("data") or []
            return self.executor.run(agent_name, q or original_question, data=data)

        if agent_name == "dashboard_agent":
            payload: dict[str, Any] = {}
            if q:
                payload["question"] = q
            if "data" in p and p["data"]:
                payload["data"] = p["data"]
            if "max_charts" in p:
                payload["max_charts"] = p["max_charts"]
            if "include_kpi" in p:
                payload["include_kpi"] = bool(p["include_kpi"])
            if not payload.get("question"):
                payload["question"] = original_question
            req = DashboardRequest(**payload)
            return self.executor.run(agent_name, req)

        if agent_name == "presentation_agent":
            # PresentationAgent.run очень толерантный, но мы даём ему безопасный shape.
            # Поддерживаем как {"questions": [...]}, так и {"question": "..."} от LLM.
            if "questions" in p and p["questions"]:
                qs: Any = p["questions"]
            elif q:
                qs = [q]
            else:
                qs = [original_question] if original_question else []
            # Можно передать list[str] — PresentationAgent сам превратит в внутренний список.
            # Если в будущем понадобятся per-question prefs (chart_type), здесь можно собрать
            # list[dict] или PresentationInput, но для планов от Главного агента list[str] достаточно.
            return self.executor.run(agent_name, qs)

        # Неизвестный агент или fallback — пусть executor обернёт ошибку
        return self.executor.run(agent_name, p if p else original_question)

    def _execute_plan(self, plan: Plan, original_question: str) -> AgentResult:
        """Выполняет план с надёжной передачей контекста.

        - Уважает зависимости (топологический порядок).
        - При ошибке в одной задаче пытается продолжить независимые задачи.
        - Собирает краткие саммари для красивого отображения в UI.
        - Использует _invoke_agent для корректных форм аргументов под каждый тип run().
        """
        context: dict[str, Any] = {}
        executed_calls: list[AgentCall] = []
        plan_execution: list[dict] = []  # для UI: статус + brief_result

        ordered = self._topological_sort(plan.tasks)

        for task in ordered:
            task_params = dict(task.params or {})

            # Передаём контекст из зависимостей (даже если предыдущая задача частично упала).
            # Инжектим ТОЛЬКО полезные примитивы (data, source_sql). Полные объекты result_from_*
            # больше не кладём в params — они мешали нормализации и не нужны leaf-агентам.
            for dep_id in task.depends_on:
                if dep_id in context:
                    dep_res = context[dep_id]
                    if dep_res is not None:
                        if hasattr(dep_res, "data") and getattr(dep_res, "data", None):
                            task_params.setdefault("data", dep_res.data)
                        if hasattr(dep_res, "sql"):
                            task_params.setdefault("source_sql", dep_res.sql)
                        # Больше не делаем: task_params[f"result_from_{dep_id}"] = dep_res

            try:
                start_ts = time.time()
                res = self._invoke_agent(task.agent_name, task_params, original_question)
                duration = int((time.time() - start_ts) * 1000)

                success = getattr(res, "success", True)
                context[task.id] = res

                # Краткий результат для UI
                brief = self._make_brief_result(res, task.agent_name)

                plan_execution.append(
                    {
                        "num": len(plan_execution) + 1,
                        "agent_name": task.agent_name,
                        "description": task.description,
                        "status": "успешно" if success else "ошибка",
                        "brief_result": brief,
                        "depends_on": task.depends_on or [],
                    }
                )

                # Для логов/трассировки показываем, что именно передали (без огромных объектов)
                input_summary = str(
                    {k: v for k, v in task_params.items() if not str(k).startswith("result_from_")}
                )[:250]

                executed_calls.append(
                    AgentCall(
                        agent_name=task.agent_name,
                        input_summary=input_summary,
                        success=success,
                        duration_ms=duration,
                        reasoning=getattr(res, "reasoning", ""),
                        output_summary=brief,
                    )
                )
                logger.info(f"[PlannerAgent] task {task.id} ({task.agent_name}) → {brief}")

            except Exception as ex:
                logger.error(f"[PlannerAgent] task {task.id} ({task.agent_name}) failed: {ex}")
                err = AgentResult(
                    success=False, error=str(ex), reasoning=f"Ошибка в задаче {task.id}"
                )
                context[task.id] = err

                plan_execution.append(
                    {
                        "num": len(plan_execution) + 1,
                        "agent_name": task.agent_name,
                        "description": task.description,
                        "status": "ошибка",
                        "brief_result": f"Ошибка: {str(ex)[:100]}",
                        "depends_on": task.depends_on or [],
                    }
                )

                executed_calls.append(
                    AgentCall(
                        agent_name=task.agent_name,
                        input_summary=str(task_params)[:250],
                        success=False,
                        error=str(ex),
                    )
                )

        last_task = ordered[-1] if ordered else None
        final_result = (
            context.get(last_task.id)
            if last_task
            else AgentResult(success=False, error="План не содержал задач")
        )

        # Прикрепляем данные для UI (экспандер "Что было сделано" + история)
        try:
            if final_result is not None:
                final_result._executed_plan = plan
                final_result._plan_execution = plan_execution
                final_result._agent_calls = executed_calls
        except Exception:
            pass

        return final_result

    def _make_brief_result(self, res: Any, agent_name: str) -> str:
        """Генерирует короткое человекочитаемое описание результата задачи."""
        if res is None:
            return "Нет результата"

        if not getattr(res, "success", True):
            return f"Ошибка: {getattr(res, 'error', 'неизвестно')}"

        if hasattr(res, "data") and getattr(res, "data", None):
            n = len(res.data)
            return f"Получено {n} строк данных"
        if hasattr(res, "chart_spec") and getattr(res, "chart_spec", None):
            ctype = getattr(res.chart_spec, "chart_type", "?")
            return f"Построен график типа {ctype}"
        if hasattr(res, "pptx_path"):
            n = getattr(res, "num_slides", "?")
            return f"Создана презентация из {n} слайдов"
        if hasattr(res, "insights") and getattr(res, "insights", None):
            return "Сформированы текстовые выводы и инсайты"
        if hasattr(res, "kpi_cards") and getattr(res, "kpi_cards", None):
            n = len(res.kpi_cards)
            return f"Сформирован дашборд с {n} KPI-карточками"

        return f"Задача {agent_name} выполнена"

    def _topological_sort(self, tasks: list[Task]) -> list[Task]:
        """Простая сортировка с учётом зависимостей (для ≤3 задач)."""
        ordered: list[Task] = []
        remaining = {t.id: t for t in tasks}

        while remaining:
            progress = False
            for tid, task in list(remaining.items()):
                if all(dep in [t.id for t in ordered] for dep in task.depends_on):
                    ordered.append(task)
                    del remaining[tid]
                    progress = True
            if not progress:
                ordered.extend(remaining.values())
                break
        return ordered

    def generate_plan(self, question: str) -> Plan:
        """Только генерирует план (без выполнения). Используется для показа пользователю перед подтверждением."""
        return self._generate_plan(question)

    def execute_plan(self, plan: Plan) -> AgentResult:
        """Выполняет уже готовый план и возвращает результат.
        Прикрепляет _executed_plan и _plan_execution для отображения в UI.
        """
        return self._execute_plan(plan, getattr(plan, "goal", ""))

    def run(self, question: str) -> AgentResult:
        """Главная точка входа (автоматический режим: генерирует план и сразу выполняет).

        Для интерактивного сценария с подтверждением используйте:
            plan = planner.generate_plan(question)
            # показать пользователю + кнопки подтверждения
            result = planner.execute_plan(plan)
        """
        logger.info(f"[PlannerAgent] start (v2.5): question={question[:70]}...")

        cache_key = question.strip().lower()[:120]
        if cache_key in self._cache:
            logger.info("[PlannerAgent] cache hit")
            return self._cache[cache_key]

        try:
            plan = self._generate_plan(question)
            result = self._execute_plan(plan, question)

            if getattr(result, "success", True):
                self._cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"[PlannerAgent] run failed: {e}")
            return AgentResult(
                success=False,
                reasoning="Не удалось построить или выполнить план. Попробуйте переформулировать вопрос.",
                error=str(e),
            )

    def get_capabilities(self) -> dict:
        """Возвращает возможности агента (для introspection и будущего использования Planner'ом более высокого уровня)."""
        return {
            "name": self.name,
            "description": self.description,
            "max_tasks_per_plan": 3,
            "features": [
                "high-quality minimal plan generation (strong prompt + examples + minimization rules)",
                "automatic plan validation + LLM self-correction",
                "simple plan quality scoring",
                "dependency-aware execution with context passing",
                "per-task graceful error handling",
                "rich structured execution summary for UI",
            ],
        }
