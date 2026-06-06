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
    """PlannerAgent v2 — иерархический планировщик.

    Анализирует вопрос, генерирует Plan (1-3 задачи), выполняет его с передачей
    контекста между задачами и поддержкой зависимостей.

    Пользователь видит только финальный результат + свёрнутый список шагов плана.
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

    def _generate_plan(self, question: str) -> Plan:
        """Генерирует план (максимум 3 задачи) с помощью LLM."""
        prompt = f"""Ты — планировщик для мультиагентной BI-системы налоговой аналитики (синтетические данные РБ).

Вопрос пользователя: {question}

Разбей задачу на **1–3 шага** (задач). Используй только эти агенты:
- data_agent — получить сырые данные (возвращает sql + data)
- chart_agent — построить один график (требует данные)
- analyst_agent — текстовые выводы и инсайты (требует данные)
- dashboard_agent — комплексный дашборд (KPI + несколько графиков)
- presentation_agent — собрать .pptx презентацию

Для каждой задачи укажи:
- id (t1, t2, t3)
- description (коротко на русском)
- agent_name
- params (что передать; можно ссылаться на результат предыдущей задачи)
- depends_on (список id предыдущих задач, если нужны их результаты)

Верни строго по схеме _PlanSpec. Не больше 3 задач.
"""

        try:
            plan_spec: _PlanSpec = call_structured(
                prompt,
                schema=_PlanSpec,
                system="Ты точный планировщик. Максимум 3 задач. Отвечай только валидным JSON по схеме.",
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
            logger.info(f"[PlannerAgent] generated plan with {len(tasks)} task(s)")
            return plan

        except Exception as e:
            logger.warning(
                f"[PlannerAgent] plan generation failed: {e}. Using fallback 1-task plan."
            )
            return Plan(
                goal=question,
                tasks=[
                    Task(
                        id="t1",
                        description="Построить дашборд по запросу пользователя",
                        agent_name="dashboard_agent",
                        params={"question": question},
                    )
                ],
                strategy="Fallback: прямой вызов дашборда",
            )

    def _execute_plan(self, plan: Plan, original_question: str) -> AgentResult:
        """Выполняет план с передачей контекста. Возвращает результат последней задачи."""
        context: dict[str, Any] = {}
        executed_calls: list[AgentCall] = []

        ordered = self._topological_sort(plan.tasks)

        for task in ordered:
            task_params = dict(task.params or {})
            for dep_id in task.depends_on:
                if dep_id in context:
                    dep_res = context[dep_id]
                    if hasattr(dep_res, "data"):
                        task_params.setdefault("data", dep_res.data)
                    if hasattr(dep_res, "sql"):
                        task_params.setdefault("source_sql", dep_res.sql)
                    task_params[f"result_from_{dep_id}"] = dep_res

            call_arg = task_params if task_params else original_question

            try:
                start_ts = time.time()
                res = self.executor.run(task.agent_name, call_arg)
                duration = int((time.time() - start_ts) * 1000)

                context[task.id] = res

                executed_calls.append(
                    AgentCall(
                        agent_name=task.agent_name,
                        input_summary=str(call_arg)[:250],
                        success=getattr(res, "success", True),
                        duration_ms=duration,
                        reasoning=getattr(res, "reasoning", ""),
                        output_summary=str(res)[:200]
                        if not hasattr(res, "model_dump")
                        else "structured result",
                    )
                )
                logger.info(f"[PlannerAgent] executed task {task.id} ({task.agent_name})")

            except Exception as ex:
                logger.error(f"[PlannerAgent] task {task.id} ({task.agent_name}) failed: {ex}")
                err = AgentResult(
                    success=False, error=str(ex), reasoning=f"Ошибка в задаче {task.id}"
                )
                context[task.id] = err
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

        # Прикрепляем план для UI (duck typing)
        try:
            if final_result is not None:
                final_result._executed_plan = plan
                final_result._agent_calls = executed_calls
        except Exception:
            pass

        return final_result

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

    def run(self, question: str) -> AgentResult:
        """Главная точка входа Planner v2.

        1. Генерирует Plan (1-3 задачи).
        2. Выполняет план с передачей контекста между задачами.
        3. Возвращает результат последней задачи (с прикреплённым планом для UI).

        Пользователь видит только финальный результат + свёрнутый план в экспандере.
        """
        logger.info(f"[PlannerAgent] start (v2): question={question[:70]}...")

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
        return {
            "name": self.name,
            "description": self.description,
            "max_tasks_per_plan": 3,
            "features": [
                "plan generation (1-3 tasks)",
                "dependency-aware execution",
                "context passing between tasks",
                "simple parallelization for independent tasks",
                "graceful degradation on task failure",
            ],
        }
