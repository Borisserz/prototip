"""Orchestrator (Phase 5+): единая точка входа ask(question) и dashboard(...).

ask() делегирует планирование и параллельное выполнение в PlannerAgent.
dashboard() вызывает dashboard_agent через общий AgentExecutor из фабрики.

Возвращает AskResult / DashboardResult со всеми артефактами.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.agents.factory import get_executor
from app.schemas import AskResult, DashboardResult
from core.llm import setup_logging

setup_logging()
logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """Высокоуровневый оркестратор (Phase 5+).

    Публичные методы:
      - ask(question) -> AskResult
      - dashboard(...) -> DashboardResult
    """

    def __init__(self) -> None:
        self.out_dir = Path("out")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.executor = get_executor(include_planner=True)

    def ask(self, question: str) -> AskResult:
        """Главная точка входа через PlannerAgent.

        Planner генерирует граф задач и выполняет независимые ветки параллельно.
        Для UI сохраняется контракт AskResult: data, analysis, chart_spec, png_path.
        """
        start = time.time()
        logger.info(f"[Orchestrator] planner start: question={question[:60]}...")
        from app.agents.planner_agent import PlannerAgent

        planner = PlannerAgent()
        res = planner.run(question)
        if isinstance(res, AskResult):
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[Orchestrator] planner end: AskResult ({elapsed}ms)")
            return res

        fallback = AskResult(
            question=question,
            sql=getattr(res, "source_sql", "") or "",
            data=getattr(res, "data", []) or [],
            reasoning=getattr(res, "reasoning", "PlannerAgent вернул не-AskResult"),
            error=getattr(res, "error", None),
            success=getattr(res, "success", True),
        )
        try:
            fallback._planner_result = res
            fallback._executed_plan = getattr(res, "_executed_plan", None)
            fallback._plan_execution = getattr(res, "_plan_execution", None)
            fallback._agent_calls = getattr(res, "_agent_calls", None)
        except Exception:
            pass
        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[Orchestrator] planner end: fallback AskResult ({elapsed}ms)")
        return fallback

    def dashboard(
        self,
        question: str,
        max_charts: int = 4,
        include_kpi: bool = True,
        data: list[dict] | None = None,
    ) -> DashboardResult:
        """Единая точка для дашбордов (peer к ask).

        data можно передать, чтобы избежать повторного DataAgent (для UX фильтров/кэша).
        """
        start = time.time()
        logger.info(f"[Orchestrator] dashboard start: question={question[:60]}... max={max_charts}")
        from app.schemas import DashboardRequest

        req = DashboardRequest(
            question=question, max_charts=max_charts, include_kpi=include_kpi, data=data
        )
        res = self.executor.run("dashboard_agent", req)
        elapsed = int((time.time() - start) * 1000)
        logger.info(
            f"[Orchestrator] dashboard end: charts={len(getattr(res, 'charts', []))} kpis={len(getattr(res, 'kpi_cards', []))} ({elapsed}ms)"
        )
        return res  # type: ignore[return-value]
