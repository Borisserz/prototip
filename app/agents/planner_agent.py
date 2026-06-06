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
from app.agents.models import AgentCall, AgentResult, Plan, Task
from core.llm import call_structured, setup_logging

setup_logging()
logger = logging.getLogger("PlannerAgent")

PLAN_GENERATION_PROMPT = """Ты — эксперт-планировщик для локальной мультиагентной BI-платформы налоговой аналитики Республики Беларусь (синтетические данные).

Пользователь задал вопрос: {question}

Твоя задача — создать **минимально необходимый** план из **1, 2 или максимум 3 задач**, используя только эти агенты:

- **data_agent**: получить сырые данные по вопросу (возвращает SQL + список записей). Нужен почти всегда как первый шаг для графиков.
- **chart_agent**: построить **один** красивый график (bar, line, donut и т.д.). Требует данные из data_agent.
- **analyst_agent**: сгенерировать 3-4 текстовых инсайта/выводов на русском. Требует данные.
- **dashboard_agent**: построить **комплексный дашборд** (KPI-карточки + 3-5 взаимосвязанных графиков + layout). Может работать самостоятельно, внутри сам вызывает data/chart/analyst.
- **presentation_agent**: собрать готовую .pptx-презентацию (титульный + слайды с графиками + выводы). Принимает список вопросов или один свободный текст.

**Правила создания хорошего плана (очень важно!):**
- Делай **как можно меньше задач**. Если вопрос можно решить одним dashboard_agent или presentation_agent — делай 1 задачу.
- Используй data_agent + chart_agent только когда нужен именно "один конкретный график" (а не обзор).
- Если нужен обзор/дашборд — предпочитай dashboard_agent (1 задача).
- Если нужна презентация — используй presentation_agent (1 задача), она сама разберёт вопрос.
- dependencies (depends_on) указывай только когда задача реально нуждается в результате предыдущей (например chart_agent зависит от data_agent).
- params для каждой задачи: обычно {{"question": "..."}}. Для chart_agent после data_agent можно передать данные через контекст (не нужно явно в params).
- Все описания на русском, короткие и понятные.
- Стратегия — 1-2 предложения, почему именно такой набор задач.

**Примеры хороших планов:**

Вопрос: "Какая задолженность по регионам?"
→ 1 задача: dashboard_agent (даст топ + структуру + динамику сразу)

Вопрос: "Построй график динамики начислений в г. Минск"
→ 2 задачи: data_agent → chart_agent

Вопрос: "Сделай презентацию по налогам за 2024"
→ 1 задача: presentation_agent

**Примеры плохих планов (избегай):**
- 3 задачи, когда достаточно 1 дашборда.
- Забывать data_agent перед chart_agent.
- Слишком много зависимостей без необходимости.

Верни **строго** валидный JSON по схеме _PlanSpec. Не добавляй текст вне JSON.
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
    tasks: list[_TaskSpec] = Field(..., max_items=3, description="Список задач (максимум 3)")
    strategy: str = Field(default="", description="Краткое описание стратегии плана")


class PlannerAgent(BaseAgent):
    """PlannerAgent v2.5 — улучшенный иерархический планировщик.

    Основные улучшения по сравнению с v2:
    - Значительно более качественный промпт генерации плана (правила минимизации,
      примеры хороших/плохих планов, чёткое понимание возможностей агентов).
    - Валидация плана + self-correction (LLM исправляет ошибки и неоптимальные планы).
    - Богатое отображение выполнения (_plan_execution): статус + краткий результат каждого шага.
    - Усиленная обработка ошибок при выполнении (продолжение независимых задач).
    - Лучшее логирование и документирование.

    Пользователь видит только финальный результат + свёрнутый экспандер
    "Что было сделано" с подробной информацией по каждому шагу плана.
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

    def _generate_plan(self, question: str) -> Plan:
        """Генерирует качественный минимальный план (1-3 задачи) с помощью LLM + валидация + self-correction."""
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

            # Валидация
            errors = self._validate_plan(plan)
            if errors:
                logger.info(
                    f"[PlannerAgent] plan validation errors: {errors}. Trying self-correction..."
                )

                # Self-correction: просим LLM исправить план
                correction_prompt = f"""План содержит ошибки:
{chr(10).join("- " + e for e in errors)}

Оригинальный вопрос пользователя: {question}

Исправь план так, чтобы он стал валидным и минимальным. Верни исправленный _PlanSpec.
"""
                try:
                    corrected_spec: _PlanSpec = call_structured(
                        correction_prompt,
                        schema=_PlanSpec,
                        system="Исправь план. Только валидный JSON по схеме.",
                    )
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
                        strategy=corrected_spec.strategy or "Исправленный план",
                    )
                    logger.info("[PlannerAgent] plan self-corrected successfully")
                except Exception as corr_e:
                    logger.warning(
                        f"[PlannerAgent] self-correction also failed: {corr_e}. Using original (may be invalid)."
                    )

            logger.info(
                f"[PlannerAgent] generated plan with {len(plan.tasks)} task(s): {plan.strategy}"
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

    def _execute_plan(self, plan: Plan, original_question: str) -> AgentResult:
        """Выполняет план с надёжной передачей контекста.

        - Уважает зависимости (топологический порядок).
        - При ошибке в одной задаче пытается продолжить независимые задачи.
        - Собирает краткие саммари для красивого отображения в UI.
        """
        context: dict[str, Any] = {}
        executed_calls: list[AgentCall] = []
        plan_execution: list[dict] = []  # для UI: статус + brief_result

        ordered = self._topological_sort(plan.tasks)

        for task in ordered:
            task_params = dict(task.params or {})

            # Передаём контекст из зависимостей (даже если предыдущая задача частично упала)
            for dep_id in task.depends_on:
                if dep_id in context:
                    dep_res = context[dep_id]
                    if dep_res is not None:
                        if hasattr(dep_res, "data") and getattr(dep_res, "data", None):
                            task_params.setdefault("data", dep_res.data)
                        if hasattr(dep_res, "sql"):
                            task_params.setdefault("source_sql", dep_res.sql)
                        task_params[f"result_from_{dep_id}"] = dep_res

            call_arg = task_params if task_params else original_question

            try:
                start_ts = time.time()
                res = self.executor.run(task.agent_name, call_arg)
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

                executed_calls.append(
                    AgentCall(
                        agent_name=task.agent_name,
                        input_summary=str(call_arg)[:250],
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
                        input_summary=str(call_arg)[:250],
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

        # Прикрепляем данные для UI
        try:
            if final_result is not None:
                final_result._executed_plan = plan
                final_result._plan_execution = plan_execution  # богатая информация для экспандера
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
        """Возвращает возможности агента (для introspection / будущего использования)."""
        return {
            "name": self.name,
            "description": self.description,
            "max_tasks_per_plan": 3,
            "features": [
                "high-quality plan generation with LLM + validation + self-correction",
                "dependency-aware execution with reliable context passing",
                "per-task error handling (continues independent tasks)",
                "rich execution summary (_plan_execution) for UI",
                "simple in-memory caching",
            ],
        }
