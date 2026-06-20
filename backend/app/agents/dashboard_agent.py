"""DashboardAgent (next sprint): вопрос на русском → комплексный дашборд.

Возвращает DashboardResult:
- title + summary
- kpi_cards (детерминированные + LLM)
- 3–5 ChartSpec (через structured + переиспользование логики ChartAgent)
- layout рекомендация
- insights (высокоуровневые, частично от AnalystAgent)
- reasoning (прозрачность выбора)

Spec-first: LLM выдаёт только Pydantic-спецификации. Рендер графиков — строго через viz/charts.py.
Может вызывать DataAgent (если нет данных), AnalystAgent и ChartAgent внутри.
Весь текст на русском. Structured output, temperature=0.

Логирование в едином стиле проекта.
Graceful degradation при ошибках под-агентов.
"""

from __future__ import annotations

import logging
import time

from pydantic import BaseModel

from app.agents.base_agent import BaseAgent
from app.agents.factory import get_executor
from app.agents.models import (
    DashboardLayout,
    DashboardRequest,
    DashboardResult,
    KpiCard,
)
from app.chart_repair import repair_chart_spec
from app.pipeline_progress import emit_pipeline_stage
from core.llm import call_structured, setup_logging
from core.models import ChartSpec
from viz.style import format_number_ru

# Ensure central logging (idempotent)
setup_logging()
logger = logging.getLogger("DashboardAgent")


from app.agents.config_loader import get_agent_config

# Внутренняя схема для structured-вызова LLM (полный состав дашборда)
class _DashboardComposition(BaseModel):
    """То, что возвращает LLM в одном structured вызове.
    chart_ideas используются для реального вызова ChartAgent (reuse его FEW_SHOT + валидации).
    """

    title: str
    summary: str
    kpi_cards: list[KpiCard] = []
    charts: list[ChartSpec] = []  # fallback если нет идей
    chart_ideas: list[
        str
    ] = []  # предпочтительно: естественные под-вопросы или "Top debt horizontal_bar"
    layout: DashboardLayout
    insights: list[str] = []
    recommendations: list[str] = []
    reasoning: str


class DashboardAgent(BaseAgent):
    """Агент построения комплексных дашбордов (несколько графиков + KPI + аналитика)."""

    name = "dashboard_agent"
    description = "По вопросу строит дашборд: вызывает Data/Analyst/Chart (reuse), получает 3-5 ChartSpec + KPI + layout + insights + reasoning. Spec-first, graceful degradation."

    def run(self, request: DashboardRequest) -> DashboardResult:
        """Основной вход: вопрос → полный DashboardResult.

        Стратегия (spec-first + reuse):
        1. При необходимости получить данные через DataAgent.
        2. Получить текстовые insights через AnalystAgent (опционально, graceful).
        3. Один structured вызов LLM для композиции дашборда (title, summary, layout, kpi, charts как ChartSpec[], insights, reasoning).
           Используем мощный FEW_SHOT + примеры реальных колонок.
        4. Пост-обработка: валидация колонок, ограничение max_charts, детерминированные KPI enhancements.
        5. Сборка финального DashboardResult.
        """
        start = time.time()
        q = request.question.strip()
        logger.info(
            f"[DashboardAgent] start: question={q[:70]}... max_charts={request.max_charts} include_kpi={request.include_kpi}"
        )

        # 1. Данные (capture sql for result too)
        data: list[dict] = request.data or []
        source_sql: str | None = None
        data_source = "provided"
        if not data:
            try:
                from app.agents.models import DataAgentInput

                emit_pipeline_stage("sql", "running", "Загрузка данных для дашборда...", agent="dashboard_agent")
                dd = request.drilldown_filters
                data_req: str | DataAgentInput = (
                    DataAgentInput(question=q, drilldown_filters=dd) if dd else q
                )
                sql_res = get_executor(include_planner=False).run("data_agent", data_req)
                if not sql_res.success:
                    raise RuntimeError(sql_res.error or "DataAgent failed")
                data = sql_res.data
                source_sql = getattr(sql_res, "sql", None)
                data_source = "data_agent"
                logger.info(f"[DashboardAgent] data: fetched via DataAgent, rows={len(data)}")
            except Exception as e:
                logger.info(
                    f"[DashboardAgent] data_error: {e} — continuing with empty data (graceful)"
                )
                data = []

        if not data:
            # Минимальный валидный результат при полном отсутствии данных
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[DashboardAgent] end: no_data_fallback ({elapsed}ms)")
            return DashboardResult(
                title="Дашборд по запросу",
                summary="Не удалось получить данные для построения дашборда. Попробуйте переформулировать вопрос или проверить доступность датасета.",
                kpi_cards=[],
                charts=[],
                layout=DashboardLayout(type="single_column", columns=1),
                insights=[
                    "Данные по запросу отсутствуют.",
                    "Возможно, нужны более широкие фильтры или другой период.",
                ],
                data=[],
                source_sql=source_sql,
                reasoning="Fallback: DataAgent не вернул строк. Дашборд минимальный, чтобы UI не падал.",
            )

        # 2. Insights от AnalystAgent (опционально, для качества)
        insights: list[str] = []
        try:
            emit_pipeline_stage(
                "synthesis",
                "running",
                "AnalystAgent: текстовые инсайты для дашборда...",
                agent="dashboard_agent",
            )
            analysis = get_executor(include_planner=False).run("analyst_agent", q, data=data)
            if not analysis.success:
                raise RuntimeError(analysis.error or "AnalystAgent failed")
            insights = analysis.insights or []
            emit_pipeline_stage(
                "synthesis",
                "done",
                f"Получено инсайтов: {len(insights)}",
                agent="dashboard_agent",
            )
            logger.info(f"[DashboardAgent] analyst: got {len(insights)} insights")
        except Exception as e:
            logger.info(f"[DashboardAgent] analyst_error: {e} — will use LLM insights only")
            emit_pipeline_stage(
                "synthesis",
                "error",
                "AnalystAgent недоступен — продолжаем с LLM",
                agent="dashboard_agent",
                error=str(e),
            )
            insights = []

        # 3. Подготовка промпта + structured вызов для композиции
        emit_pipeline_stage(
            "viz",
            "running",
            "Компоновка KPI и спецификаций графиков...",
            agent="dashboard_agent",
        )
        
        # Phase 20: Pervasive RAG (Dashboard Templates)
        rag_context = ""
        try:
            from app.services.rag_service import search_dashboards
            docs = search_dashboards(q, k=1)
            if docs:
                rag_context = "\n\n[РЕФЕРЕНСНЫЙ ДАШБОРД (RAG)]\nНайден сохраненный дашборд из истории. Используй его как ВДОХНОВЕНИЕ для стилистики и уровня детализации. СТРОГО ЗАПРЕЩЕНО копировать названия графиков (titles) или chart_ideas из референса! Ты обязан придумать свои уникальные chart_ideas, которые на 100% соответствуют текущему вопросу и данным:\n" + docs[0].page_content
        except Exception as e:
            logger.info(f"[DashboardAgent] rag_error: {e}")

        sample = data[:6]
        total_rows = len(data)
        columns = list(data[0].keys()) if data else []

        # Ограничим max_charts в промпте
        max_c = max(1, min(request.max_charts, 6))

        cfg = get_agent_config("dashboard_agent")
        
        prompt = f"""Ты — {cfg.role}. {cfg.goal}

{cfg.rules}

=== FEW-SHOT EXAMPLES ===
{cfg.few_shot}

Пользовательский вопрос: {q}
Доступные колонки в данных: {columns}
Всего строк в результате: {total_rows}
Пример данных (первые строки):
{sample}
{rag_context}

Сформируй комплексный дашборд:
- chart_ideas: 3–{max_c} строк (естественные аналитические бизнес-вопросы к данным для ChartAgent, напр. "Какова динамика сборов по месяцам?", "Как распределяется задолженность между регионами?", "Топ-5 проблемных инспекций"). НЕ указывай типы графиков (bar/pie и т.д.), ChartAgent выберет их сам из 12 доступных типов.
- (опционально charts как fallback)
- KPI-карточки (если include_kpi={request.include_kpi})
- Подходящий layout
- 3–6 глубоких аналитических инсайтов (используй или дополни уже имеющиеся: {insights[:3] if insights else "нет"})
- 2–4 практические бизнес-рекомендации (recommendations) на основе этих данных (что следует сделать, на что обратить внимание)
- Чёткое и прозрачное обоснование (reasoning) твоего выбора метрик и графиков

Все заголовки, insights, summary, recommendations, rationale — на русском языке.
Используй только реальные колонки из списка выше.
Верни строго валидный JSON по схеме _DashboardComposition.
"""

        system_msg = (
            f"Ты — {cfg.role}. "
            "Всегда возвращай валидный JSON по указанной схеме. "
            "Тексты на русском, профессиональные, с Br. "
            "Выбирай реалистичные и полезные комбинации графиков."
        )

        try:
            composition = call_structured(
                prompt,
                schema=_DashboardComposition,
                system=system_msg,
                agent_name=self.name
            )
            logger.info(
                f"[DashboardAgent] llm_composition: charts={len(composition.charts)} kpis={len(composition.kpi_cards)} layout={composition.layout.type}"
            )
        except Exception as e:
            logger.info(f"[DashboardAgent] llm_error: {e}")
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[DashboardAgent] end_error_fallback ({elapsed}ms)")
            # Graceful минимальный дашборд
            return self._fallback_result(q, data, insights, str(e), source_sql=source_sql)

        # 4. Пост-обработка и ограничения + активация реального reuse ChartAgent (Parallel - Phase 16)
        chart_ideas = getattr(composition, "chart_ideas", None) or []
        if not chart_ideas and composition.charts:
            chart_ideas = [getattr(c, "title", str(c)) for c in composition.charts]

        charts: list[ChartSpec] = []
        try:
            executor_pipeline = get_executor(include_planner=False)
            import concurrent.futures

            def _generate_chart(idea):
                idea_str = idea if isinstance(idea, str) else getattr(idea, "title", str(idea))
                cr = executor_pipeline.run("chart_agent", idea_str, data=data)
                if not cr.success or not cr.specs:
                    raise RuntimeError(cr.error or "ChartAgent failed or returned no specs")
                return repair_chart_spec(cr.specs[0], data, question=idea_str)

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_c) as pool:
                futures = {pool.submit(_generate_chart, idea): idea for idea in (chart_ideas or [])[:max_c]}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        charts.append(future.result())
                    except Exception as e:
                        logger.info(f"[DashboardAgent] sub_chart_error: {e}")
        except Exception as e:
            logger.info(f"[DashboardAgent] chart_agent_init_error: {e}")

        if not charts and composition.charts:
            charts = [
                repair_chart_spec(c, data, question=q) for c in composition.charts[:max_c]
            ]

        # Мягкая валидация: если x/y не в данных — оставляем (модель иногда ошибается, но viz потом отработает или упадёт выше)
        if data:
            cols = set(data[0].keys())
            for c in charts:
                if c.chart_type != "kpi":
                    if c.x and c.x not in cols:
                        logger.info(f"[DashboardAgent] warn: chart x='{c.x}' not in data columns")
                    if c.y and c.y not in cols:
                        logger.info(f"[DashboardAgent] warn: chart y='{c.y}' not in data columns")

        kpi_cards = composition.kpi_cards if request.include_kpi else []

        # Детерминированное усиление KPI (если данных достаточно)
        if request.include_kpi and data and not kpi_cards:
            kpi_cards = self._compute_basic_kpis(data)

        # 5. Insights: если LLM дал мало — дополняем от Analyst
        final_insights = composition.insights or []
        if len(final_insights) < 3 and insights:
            final_insights = (final_insights + insights)[:6]

        result = DashboardResult(
            title=composition.title,
            summary=composition.summary,
            kpi_cards=kpi_cards,
            charts=charts,
            layout=composition.layout,
            insights=final_insights,
            recommendations=composition.recommendations or [],
            data=data,
            source_sql=source_sql,
            reasoning=composition.reasoning,
        )

        emit_pipeline_stage(
            "viz",
            "done",
            f"Дашборд: {len(result.charts)} графиков · {len(result.kpi_cards)} KPI",
            agent="dashboard_agent",
        )

        elapsed = int((time.time() - start) * 1000)
        logger.info(
            f"[DashboardAgent] end: title='{result.title[:40]}...' charts={len(result.charts)} kpis={len(result.kpi_cards)} ({elapsed}ms) data_source={data_source}"
        )
        return result

    def _compute_basic_kpis(self, data: list[dict]) -> list[KpiCard]:
        """Детерминированные базовые KPI из данных (всегда точные числа)."""
        try:
            import pandas as pd

            df = pd.DataFrame(data)
            cards: list[KpiCard] = []

            if "debt" in df.columns:
                total_debt = float(df["debt"].sum())
                cards.append(
                    KpiCard(
                        name="Общая задолженность",
                        value=format_number_ru(total_debt),
                        unit="",
                    )
                )
            if "accrued" in df.columns:
                total_acc = float(df["accrued"].sum())
                cards.append(
                    KpiCard(
                        name="Суммарные начисления (выборка)",
                        value=format_number_ru(total_acc),
                        unit="",
                    )
                )
            if "region" in df.columns:
                n_regions = df["region"].nunique()
                cards.append(KpiCard(name="Регионов в выборке", value=n_regions, unit=""))
            if "tax_type" in df.columns:
                n_taxes = df["tax_type"].nunique()
                cards.append(KpiCard(name="Видов налогов", value=n_taxes, unit=""))
            return cards[:4]
        except Exception:
            return []

    def _fallback_result(
        self,
        question: str,
        data: list[dict],
        insights: list[str],
        error: str,
        source_sql: str | None = None,
    ) -> DashboardResult:
        """Минимальный рабочий дашборд при ошибке LLM."""
        kpis = self._compute_basic_kpis(data) if data else []
        return DashboardResult(
            title="Дашборд: " + question[:60],
            summary="Частично сформированный дашборд из-за внутренней ошибки при генерации композиции. Использованы доступные данные.",
            kpi_cards=kpis,
            charts=[],
            layout=DashboardLayout(type="single_column", columns=1),
            insights=insights or ["Не удалось полностью проанализировать данные."],
            recommendations=["Обратитесь к администратору для проверки доступности данных."],
            data=data or [],
            source_sql=source_sql,
            reasoning=f"Fallback из-за ошибки LLM: {error[:200]}",
        )

    def run_input(self, inp: DashboardRequest) -> DashboardResult:
        """Удобный алиас для совместимости с паттернами проекта."""
        return self.run(inp)
