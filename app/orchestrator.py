"""Orchestrator (Phase 5): единая точка входа ask(question).

Прогоняет полный пайплайн:
DataAgent → AnalystAgent → ChartAgent → build_chart + export_png (в out/)

Возвращает AskResult со всеми артефактами.
Обработка ошибок на каждом шаге (не роняем весь пайплайн).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import pandas as pd

from app.agents.analyst_agent import AnalystAgent
from app.agents.chart_agent import ChartAgent
from app.agents.dashboard_agent import DashboardAgent
from app.agents.data_agent import DataAgent
from app.agents.executor import AgentExecutor, AgentRegistry
from app.agents.models import AgentResult
from app.schemas import AskResult, DashboardResult, SqlResult
from core.llm import setup_logging
from viz.charts import build_chart, export_png

# Ensure central logging
setup_logging()
logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """Высокоуровневый оркестратор (Phase 5+).

    Публичные методы (оставляем только их):
      - ask(question) -> AskResult          (вопрос → данные + анализ + один график)
      - dashboard(...) -> DashboardResult   (вопрос → KPI + несколько ChartSpec + layout + insights)

    Генерация презентаций — через PresentationAgent (он внутри создаёт Orchestrator.ask по необходимости).

    Сложная логика "что/когда/в каком порядке вызывать" и планирование
    постепенно переносится в PlannerAgent. Сейчас — простой линейный пайплайн,
    вызовы под-агентов — через AgentExecutor.
    """

    def __init__(self) -> None:
        # Прямые экземпляры (для обратной совместимости и случаев, когда нужен сам агент)
        self.data_agent = DataAgent()
        self.analyst_agent = AnalystAgent()
        self.chart_agent = ChartAgent()
        self.dashboard_agent = DashboardAgent()

        # Реестр + исполнитель (Phase 3+). Постепенная миграция вызовов на executor.
        self.registry = AgentRegistry()
        self.executor = AgentExecutor(self.registry)
        for ag in (self.data_agent, self.analyst_agent, self.chart_agent, self.dashboard_agent):
            self.executor.register(ag)

        self.out_dir = Path("out")
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _slug(self, text: str, max_len: int = 40) -> str:
        slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "_", text.lower()).strip("_")
        return slug[:max_len] or "result"

    def ask(self, question: str) -> AskResult:
        """Главная точка входа.

        Использует AgentExecutor для вызовов Data/Analyst/Chart (логирование + единообразие).
        Ошибки на шагах обрабатываются gracefully (как и раньше), чтобы вернуть частичный результат.
        """
        start = time.time()
        logger.info(f"[Orchestrator] start: question={question[:60]}...")
        result = AskResult(question=question, sql="", data=[])

        # 1. DataAgent (через executor — начало миграции)
        try:
            sql_res = self.executor.run("data_agent", question)
            if not sql_res.success or not isinstance(sql_res, SqlResult):
                # ошибка или неожиданный тип — graceful как раньше
                err = getattr(sql_res, "error", "unknown")
                result.sql = f"-- ERROR in DataAgent: {err}"
                result.data = []
                logger.info(f"[Orchestrator] data_error: {err}")
                return result
            result.sql = sql_res.sql
            result.data = sql_res.data
            logger.info(f"[Orchestrator] data: rows={len(result.data)}")
        except Exception as e:  # defensive (executor сам не должен бросать, но на всякий)
            result.sql = f"-- ERROR in DataAgent: {e}"
            result.data = []
            logger.info(f"[Orchestrator] data_error: {e}")
            return result

        # 2. AnalystAgent (через executor)
        try:
            analysis_res = self.executor.run("analyst_agent", question, data=result.data)
            if isinstance(analysis_res, AgentResult) and not analysis_res.success:
                raise RuntimeError(getattr(analysis_res, "error", "analyst failed"))
            # При успехе это AnalysisResult (наследник)
            result.analysis = analysis_res if hasattr(analysis_res, "insights") else None  # type: ignore
            if result.analysis:
                logger.info(
                    f"[Orchestrator] analyst: insights={len(result.analysis.insights) if result.analysis else 0}"
                )
        except Exception as e:
            # fallback анализ (сохраняем старое поведение)
            from app.schemas import AnalysisResult

            result.analysis = AnalysisResult(
                insights=[
                    "Не удалось выполнить полноценный анализ из-за ошибки на шаге AnalystAgent.",
                    "Рекомендуется проверить доступность модели Ollama и качество входных данных.",
                    "Дальнейшие шаги пайплайна (график) могут быть частично доступны.",
                ],
                key_conclusion=f"Ошибка AnalystAgent: {e}",
                anomaly_or_trend=None,
            )
            logger.info(f"[Orchestrator] analyst_error: {e}")

        # 3. ChartAgent (через executor)
        try:
            chart_res = self.executor.run("chart_agent", question, data=result.data)
            if isinstance(chart_res, AgentResult) and not chart_res.success:
                raise RuntimeError(getattr(chart_res, "error", "chart failed"))
            result.chart_spec = getattr(chart_res, "spec", None)
            logger.info(
                f"[Orchestrator] chart: type={getattr(result.chart_spec, 'chart_type', None)}"
            )
        except Exception as e:
            result.chart_spec = None
            logger.info(f"[Orchestrator] chart_error: {e}")
            # Можно продолжить без чарта

        # 4. Рендер графика + сохранение PNG в out/
        png_path: str | None = None
        if result.chart_spec is not None and result.data:
            try:
                df = pd.DataFrame(result.data)
                fig = build_chart(df, result.chart_spec)
                safe_name = self._slug(question)
                png_file = self.out_dir / f"chart_{safe_name}.png"
                export_png(fig, png_file, scale=2.0)
                png_path = str(png_file)
            except Exception as e:
                png_path = f"ERROR rendering: {e}"
                logger.info(f"[Orchestrator] render_error: {e}")

        result.png_path = png_path
        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[Orchestrator] end: png={bool(png_path)} ({elapsed}ms)")
        # Высокоуровневое reasoning для AskResult (пайплайн через executor)
        if not getattr(result, "reasoning", ""):
            result.reasoning = (
                f"Пайплайн: DataAgent → AnalystAgent → ChartAgent (+ viz render). "
                f"SQL rows={len(result.data)}. График: {getattr(result.chart_spec, 'chart_type', 'none')}. "
                "Все sub-вызовы через AgentExecutor."
            )
        return result

    def dashboard(
        self,
        question: str,
        max_charts: int = 4,
        include_kpi: bool = True,
        data: list[dict] | None = None,
    ) -> DashboardResult:
        """Единая точка для дашбордов (peer к ask). Переиспользует sub-агентов оркестратора + DashboardAgent.

        data можно передать, чтобы избежать повторного DataAgent (для UX фильтров/кэша).
        """
        start = time.time()
        logger.info(f"[Orchestrator] dashboard start: question={question[:60]}... max={max_charts}")
        from app.schemas import DashboardRequest

        req = DashboardRequest(
            question=question, max_charts=max_charts, include_kpi=include_kpi, data=data
        )
        # Через executor (логирование + унификация). DashboardResult — наследник AgentResult.
        res = self.executor.run("dashboard_agent", req)
        # Если по какой-то причине не DashboardResult — возвращаем как есть (executor вернёт failed AgentResult)
        elapsed = int((time.time() - start) * 1000)
        logger.info(
            f"[Orchestrator] dashboard end: charts={len(getattr(res, 'charts', []))} kpis={len(getattr(res, 'kpi_cards', []))} ({elapsed}ms)"
        )
        return res  # type: ignore[return-value]  # на практике DashboardResult или AgentResult(failed)
