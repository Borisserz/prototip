"""PlannerAgent (первая версия, Вариант A).

Простой intent-based роутер.
Принимает вопрос → определяет intent → вызывает ровно один основной агент
через AgentExecutor → возвращает его результат.

Всё происходит скрыто: пользователь не видит план, вызванные агенты
и внутренний reasoning.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.data_agent import ALLOWED_COLUMNS
from app.agents.factory import get_executor
from app.agents.models import (
    AgentCall,
    AgentResult,
    AskResult,
    DashboardRequest,
    Plan,
    Task,
)
from core.llm import call_structured, setup_logging
from viz.charts import build_chart, export_png

setup_logging()
logger = logging.getLogger("PlannerAgent")

PLAN_GENERATION_PROMPT = """Ты — эксперт-планировщик для локальной мультиагентной BI-платформы налоговой аналитики Республики Беларусь (синтетические данные 2024 года, валюта Br).

Пользователь задал вопрос: {question}

**Структура датасета (Schema Awareness) — доступные колонки:**
{allowed_columns}

**Правило Schema Awareness:** при постановке задачи для **data_agent** обязательно используй названия колонок из доступного списка в параметре "question", чтобы SQL сгенерировался максимально точно (например: region, tax_type, accrued, debt, period, penalties).

Твоя задача — создать **минимально необходимый** план из **1, 2 или максимум 3 задач**, используя только эти агенты:

Доступные агенты и их сильные стороны (используй это при выборе):
- **data_agent**: только получение сырых данных (SQL + записи). params: {{"question": "<вопрос для генерации SQL>"}}. Нужен почти всегда как подготовительный шаг, если дальше будет chart_agent или analyst_agent.
- **chart_agent**: построение **ровно одного** графика (line, horizontal_bar, donut и т.д.). Требует данные (они придут автоматически по depends_on от data_agent). params: {{"question": "<конкретный под-вопрос для этого одного графика>"}}. Используй только когда пользователь явно хочет "один график", "динамику", "топ", "сравнение двух категорий".
- **analyst_agent**: генерация 3-4 текстовых инсайтов/выводов на русском. Требует данные; если перед ним был chart_agent — получит ChartSpec и свяжет выводы с визуализацией. params: {{"question": "<вопрос>"}}.
- **dashboard_agent**: построение **комплексного дашборда** (KPI-карточки + 3-5 взаимосвязанных графиков + layout + summary). Сам внутри вызывает data/chart/analyst. **Предпочитай его**, когда пользователю нужен "обзор", "дашборд", "ключевые метрики", "сравнение нескольких показателей сразу". params: {{"question": "<оригинальный вопрос>"}} (опционально data, max_charts).
- **presentation_agent**: сборка готовой .pptx-презентации (титульный слайд + слайды с графиками + выводы + рекомендации). Принимает один вопрос или список. **Предпочитай его**, когда пользователь просит "презентацию", "отчёт", "слайды", "доклад". params: {{"question": "<тема>"}} или {{"questions": ["q1", "q2", ...]}}.

**Жёсткие правила минимизации (соблюдай в порядке приоритета):**

1. Если запрос можно полностью закрыть одной задачей — делай ровно 1 задачу.
   - Широкий обзор / несколько показателей / "дашборд" / "что происходит" → dashboard_agent.
   - Презентация / отчёт / "сделай слайды" → presentation_agent.
2. Используй цепочку data_agent → chart_agent только когда пользователь явно хочет **один конкретный график** (динамика одной серии, топ-N, один donut и т.д.).
3. Никогда не делай 3 задачи, если можно обойтись 1 или 2.
4. dashboard_agent и presentation_agent уже содержат внутри умную логику (они сами вызывают data/chart/analyst при необходимости). Не дублируй их работу.
5. depends_on указывай **обязательно**, когда следующая задача реально использует результат предыдущей. Особенно: если после data_agent идёт analyst_agent или chart_agent — depends_on должен содержать id data_agent.
6. **Diamond-паттерн (график + выводы):** если пользователю нужны И график, И текстовые выводы — строй цепочку data_agent → chart_agent → analyst_agent:
   - chart_agent.depends_on = [id data_agent]
   - analyst_agent.depends_on = [id data_agent, id chart_agent] — Аналитик синтезирует данные и визуализацию в связный нарратив.
7. Если нужен только график без выводов — достаточно data_agent → chart_agent (2 задачи).
8. Если нужен только текстовый анализ без графика — data_agent → analyst_agent (analyst зависит только от data).
9. Не добавляй лишние зависимости, но для связки «график + выводы» analyst_agent **обязан** зависеть от chart_agent.

**Примеры хороших планов (минимальных и правильных):**

Вопрос: "Какая задолженность по регионам?"
→ План: 1 задача → dashboard_agent
  (даст топ, структуру, динамику, KPI — всё в одном месте)

Вопрос: "Построй график динамики начислений в г. Минск за год"
→ План: 2 задачи → data_agent → chart_agent
  (нужен именно один график линии)

Вопрос: "Покажи данные, график и выводы по задолженности регионов"
→ План: 3 задачи → data_agent → chart_agent → analyst_agent (Diamond)
  chart_agent.depends_on=[data_task_id], analyst_agent.depends_on=[data_task_id, chart_task_id].
  data_agent params.question: "Топ регионов по задолженности (колонки region, debt)".

Вопрос: "Сделай презентацию по денежному состоянию граждан"
→ План: 1 задача → presentation_agent
  (она сама разберёт вопрос на несколько слайдов)

**Примеры хороших планов для размытых/приветственных запросов (добавлены в Phase 1):**

Вопрос: "привет дай сводку по налогам"
 План: 1 задача → dashboard_agent
  (широкий обзор — лучше всего один дашборд)

Вопрос: "краткая сводка по налогам"
 План: 1 задача → dashboard_agent
  (пользователь хочет общую картину, не один график и не цепочку)

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

    def __init__(self, use_shared_executor: bool = True) -> None:
        self.executor = get_executor(include_planner=False, fresh=not use_shared_executor)
        self.registry = self.executor.registry
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
        allowed_columns = ", ".join(sorted(ALLOWED_COLUMNS))
        prompt = PLAN_GENERATION_PROMPT.format(question=question, allowed_columns=allowed_columns)
        planner_system = (
            "Ты — точный планировщик с полным знанием схемы данных. "
            f"Доступные колонки датасета: {allowed_columns}. "
            "При задачах для data_agent в params['question'] используй реальные названия колонок. "
            "Для запросов «график + выводы» строй Diamond: data → chart → analyst. "
            "Минимизируй число задач. Отвечай только валидным JSON по схеме."
        )

        try:
            plan_spec: _PlanSpec = call_structured(
                prompt,
                schema=_PlanSpec,
                system=planner_system,
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
            tasks = self._repair_plan(tasks)

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

Доступные колонки датасета: {allowed_columns}

Сгенерированный план:
{plan.model_dump_json(indent=2)}

Проблемы, которые нужно исправить:
{chr(10).join("- " + e for e in errors) if errors else "- План можно сделать существенно короче и лучше"}

Правила, которые ты должен был соблюсти (исправляй эти нарушения в первую очередь):
- Минимум задач — если можно одним высокоуровневым агентом (dashboard_agent или presentation_agent), делай ровно 1 задачу.
- Для широких вопросов ("сводка", "обзор", "дай данные по...", "привет...") — всегда предпочитай dashboard_agent или presentation_agent.
- Не дублировать работу высокоуровневых агентов (dashboard и presentation уже сами вызывают data/chart/analyst внутри).
- **Schema Awareness**: в params["question"] для data_agent используй реальные колонки ({allowed_columns}).
- **Diamond-паттерн**: если нужны график И выводы — data → chart → analyst; analyst_agent.depends_on должен включать И data_agent, И chart_agent.
- Если после data_agent идёт chart_agent или analyst_agent — depends_on на id data_agent обязателен.

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
                    tasks = self._repair_plan(tasks)
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

        Это **единственное** место, которое знает точные сигнатуры run() всех агентов
        и как превращать Task.params + инжектированный контекст в корректный вызов.

        - data_agent: run(question: str)
        - chart_agent: run(question: str, data: list[dict])
        - analyst_agent: run(question: str, data: list[dict], chart_spec: dict | None)
        - dashboard_agent: run(request: DashboardRequest)
        - presentation_agent: run(questions: list[str] | PresentationInput | ...)

        Здесь же — defensive извлечение question, гарантия data для data-зависимых агентов,
        и подробный лог того, что именно было передано (очень помогает при отладке "почему упал").
        """
        p = {k: v for k, v in (params or {}).items() if not str(k).startswith("result_from_")}

        # Очень defensive извлечение вопроса (LLM иногда кладёт "q", иногда вообще ничего)
        q = (
            str(p.get("question") or p.get("q") or original_question or "").strip()
            or original_question
        )

        if agent_name == "data_agent":
            arg = q or original_question
            logger.info(f"[PlannerAgent] _invoke data_agent q={arg[:60]!r}")
            return self.executor.run(agent_name, arg)

        if agent_name == "chart_agent":
            data = p.get("data") or []
            if not data:
                logger.warning(
                    f"[PlannerAgent] _invoke chart_agent: data is EMPTY. "
                    f"Check depends_on / _repair_plan. q={q[:60]!r}"
                )
            logger.info(f"[PlannerAgent] _invoke chart_agent q={q[:50]!r} data_rows={len(data)}")
            return self.executor.run(agent_name, q or original_question, data=data)

        if agent_name == "analyst_agent":
            data = p.get("data") or []
            chart_spec = p.get("chart_spec")
            if not data:
                logger.warning(
                    f"[PlannerAgent] _invoke analyst_agent: data is EMPTY. "
                    f"Check depends_on / _repair_plan. q={q[:60]!r}"
                )
            logger.info(
                f"[PlannerAgent] _invoke analyst_agent q={q[:50]!r} "
                f"data_rows={len(data)} has_chart_spec={chart_spec is not None}"
            )
            call_kwargs: dict[str, Any] = {"data": data}
            if chart_spec is not None:
                call_kwargs["chart_spec"] = chart_spec
            return self.executor.run(agent_name, q or original_question, **call_kwargs)

        if agent_name == "dashboard_agent":
            payload: dict[str, Any] = {}
            if q:
                payload["question"] = q
            if p.get("data"):
                payload["data"] = p["data"]
            if "max_charts" in p:
                payload["max_charts"] = p["max_charts"]
            if "include_kpi" in p:
                payload["include_kpi"] = bool(p["include_kpi"])
            if not payload.get("question"):
                payload["question"] = original_question
            logger.info(
                f"[PlannerAgent] _invoke dashboard_agent question={payload.get('question', '')[:50]!r} has_data={bool(payload.get('data'))}"
            )
            req = DashboardRequest(**payload)
            return self.executor.run(agent_name, req)

        if agent_name == "presentation_agent":
            if p.get("questions"):
                qs: Any = p["questions"]
            elif q:
                qs = [q]
            else:
                qs = [original_question] if original_question else []
            logger.info(
                f"[PlannerAgent] _invoke presentation_agent questions_count={len(qs) if isinstance(qs, (list, tuple)) else '?'}"
            )
            return self.executor.run(agent_name, qs)

        # Неизвестный агент — пусть executor вернёт ошибку (будет записана в trace)
        logger.warning(f"[PlannerAgent] _invoke unknown agent {agent_name}")
        return self.executor.run(agent_name, p if p else original_question)

    def _execute_plan(self, plan: Plan, original_question: str) -> AgentResult:
        """Execute plan in dependency-aware parallel waves."""
        context: dict[str, AgentResult] = {}
        executed_calls: list[AgentCall] = []
        plan_execution: list[dict] = []
        lock = threading.Lock()

        tasks = {t.id: t for t in plan.tasks}
        pending = set(tasks.keys())
        running: dict[Any, tuple[Task, dict[str, Any], float]] = {}
        max_workers = max(1, min(4, len(tasks) or 1))

        def build_params(task: Task) -> dict[str, Any]:
            task_params = dict(task.params or {})
            with lock:
                dependency_results = [context.get(dep_id) for dep_id in task.depends_on]
            for dep_res in dependency_results:
                if dep_res is not None:
                    if hasattr(dep_res, "data") and getattr(dep_res, "data", None):
                        task_params.setdefault("data", dep_res.data)
                    if hasattr(dep_res, "sql"):
                        task_params.setdefault("source_sql", dep_res.sql)
                    if hasattr(dep_res, "spec") and getattr(dep_res, "spec", None) is not None:
                        task_params.setdefault("chart_spec", dep_res.spec.model_dump())
            return task_params

        def submit_ready(pool: ThreadPoolExecutor) -> None:
            with lock:
                completed_ids = set(context.keys())
            ready = [
                tasks[tid]
                for tid in list(pending)
                if all(dep in completed_ids for dep in tasks[tid].depends_on)
            ]
            for task in ready:
                params = build_params(task)
                future = pool.submit(self._invoke_agent, task.agent_name, params, original_question)
                running[future] = (task, params, time.time())
                pending.remove(task.id)
                logger.info(
                    f"[PlannerAgent] submitted task {task.id} ({task.agent_name}) deps={task.depends_on or []}"
                )

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="planner") as pool:
            submit_ready(pool)
            while running or pending:
                if not running:
                    with lock:
                        for tid in list(pending):
                            task = tasks[tid]
                            err = AgentResult(
                                success=False,
                                error="Не удалось выполнить задачу: зависимости не были разрешены",
                                reasoning=f"Задача {task.id} пропущена из-за unresolved dependencies",
                            )
                            context[task.id] = err
                            plan_execution.append(
                                {
                                    "num": len(plan_execution) + 1,
                                    "agent_name": task.agent_name,
                                    "description": task.description,
                                    "status": "ошибка",
                                    "brief_result": err.error,
                                    "depends_on": task.depends_on or [],
                                }
                            )
                            executed_calls.append(
                                AgentCall(
                                    agent_name=task.agent_name,
                                    input_summary=str(task.params)[:250],
                                    success=False,
                                    error=err.error,
                                )
                            )
                            pending.remove(tid)
                    break

                done, _ = wait(running.keys(), return_when=FIRST_COMPLETED)
                for future in done:
                    task, task_params, start_ts = running.pop(future)
                    duration = int((time.time() - start_ts) * 1000)
                    try:
                        res = future.result()
                    except Exception as ex:
                        logger.error(
                            f"[PlannerAgent] task {task.id} ({task.agent_name}) failed: {ex}"
                        )
                        res = AgentResult(
                            success=False,
                            error=str(ex),
                            reasoning=f"Ошибка в задаче {task.id}",
                        )

                    success = getattr(res, "success", True)
                    brief = self._make_brief_result(res, task.agent_name)
                    input_summary = str(task_params)[:250]

                    with lock:
                        context[task.id] = res
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
                                input_summary=input_summary,
                                success=success,
                                duration_ms=duration,
                                reasoning=getattr(res, "reasoning", ""),
                                error=getattr(res, "error", None),
                                output_summary=brief,
                            )
                        )
                    logger.info(f"[PlannerAgent] task {task.id} ({task.agent_name}) → {brief}")

                submit_ready(pool)

        final_result = self._aggregate_result(plan, context, original_question)

        try:
            final_result._executed_plan = plan
            final_result._plan_execution = plan_execution
            final_result._agent_calls = executed_calls
        except Exception:
            pass

        return final_result

    def _aggregate_result(
        self, plan: Plan, context: dict[str, AgentResult], original_question: str
    ) -> AgentResult:
        """Aggregate parallel task outputs into the most UI-compatible result."""
        results_in_plan_order = [context[t.id] for t in plan.tasks if t.id in context]
        successful = [r for r in results_in_plan_order if getattr(r, "success", True)]

        for agent_name in ("dashboard_agent", "presentation_agent"):
            for task in plan.tasks:
                if task.agent_name == agent_name and task.id in context:
                    return context[task.id]

        data_res = next(
            (context[t.id] for t in plan.tasks if t.agent_name == "data_agent" and t.id in context),
            None,
        )
        analysis_res = next(
            (
                context[t.id]
                for t in plan.tasks
                if t.agent_name == "analyst_agent" and t.id in context
            ),
            None,
        )
        chart_res = next(
            (
                context[t.id]
                for t in plan.tasks
                if t.agent_name == "chart_agent" and t.id in context
            ),
            None,
        )

        if data_res is not None and (analysis_res is not None or chart_res is not None):
            result = AskResult(question=original_question, sql="", data=[])
            result.sql = getattr(data_res, "sql", "") or ""
            result.data = getattr(data_res, "data", []) or []
            if analysis_res is not None and hasattr(analysis_res, "insights"):
                result.analysis = analysis_res  # type: ignore[assignment]
            if chart_res is not None and hasattr(chart_res, "spec"):
                result.chart_spec = chart_res.spec

            if result.chart_spec is not None and result.data:
                try:
                    out_dir = Path("out")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    df = pd.DataFrame(result.data)
                    fig = build_chart(df, result.chart_spec)
                    png_file = out_dir / f"chart_{self._slug(original_question)}.png"
                    export_png(fig, png_file, scale=2.0)
                    result.png_path = str(png_file)
                except Exception as e:
                    result.png_path = f"ERROR rendering: {e}"
                    logger.info(f"[PlannerAgent] aggregate render_error: {e}")

            result.reasoning = (
                "PlannerAgent выполнил граф задач (Diamond или параллельные ветки) "
                "и агрегировал Data/Chart/Analyst в AskResult для совместимости с UI."
            )
            return result

        if successful:
            return successful[-1]
        if results_in_plan_order:
            return results_in_plan_order[-1]
        return AgentResult(success=False, error="План не содержал исполнимых задач")

    def _slug(self, text: str, max_len: int = 40) -> str:
        import re

        slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "_", text.lower()).strip("_")
        return slug[:max_len] or "result"

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

    def _repair_plan(self, tasks: list[Task]) -> list[Task]:
        """Пост-обработка плана после генерации LLM (и после self-correction).

        Делает план максимально исполнимым даже если модель что-то упустила:
        - Гарантирует, что analyst/chart после data_agent имеют depends_on на него (data flow).
        - Гарантирует наличие usable "question" в params для задач, которым он нужен.
        - Можно расширять под другие частые ошибки LLM (max 3 tasks уже ограничено в схеме).

        Это основная защита от симптома "data_agent получил строки, а analyst/chart их не увидел".
        """
        fixed: list[Task] = []
        data_ids = [t.id for t in tasks if t.agent_name == "data_agent"]
        chart_ids = [t.id for t in tasks if t.agent_name == "chart_agent"]
        last_data_id = data_ids[0] if data_ids else None
        last_chart_id = chart_ids[0] if chart_ids else None

        for t in tasks:
            params = dict(t.params or {})
            deps = list(t.depends_on or [])

            if t.agent_name == "chart_agent" and last_data_id and last_data_id not in deps:
                deps.append(last_data_id)

            if t.agent_name == "analyst_agent":
                if last_data_id and last_data_id not in deps:
                    deps.append(last_data_id)
                if last_chart_id and last_chart_id not in deps:
                    deps.append(last_chart_id)

            # Ремонт "question" — самая частая недостача в params от LLM
            if not params.get("question"):
                # Для большинства задач достаточно оригинального вопроса пользователя.
                # Более точный под-вопрос (если модель его сгенерировала) мы оставляем.
                # Здесь мы просто гарантируем наличие ключа, чтобы _invoke_agent не падал.
                # Конкретное значение будет взято в _invoke_agent (original_question фоллбэк).
                params["question"] = params.get("question") or ""

            fixed.append(
                Task(
                    id=t.id,
                    description=t.description,
                    agent_name=t.agent_name,
                    params=params,
                    depends_on=deps,
                )
            )

        return fixed

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
