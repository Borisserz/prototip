"""Orchestrator: единая точка входа ask / dashboard / presentation.

ask() делегирует PlannerAgent (singleton, shared executor).
dashboard() и presentation() — прямые вызовы через AgentExecutor.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.factory import get_executor, get_planner
from app.agents.models import AgentResult
from app.config import config
from app.logging_utils import get_correlation_id, new_correlation_id, run_logger
from app.schemas import (
    AskResult,
    DashboardRequest,
    DashboardResult,
    DrilldownContext,
    PresentationInput,
    PresentationResult,
)
from core.llm import setup_logging

setup_logging()
logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """Высокоуровневый оркестратор — единый фасад для UI, API и CLI."""

    def __init__(self) -> None:
        self.out_dir = config.out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.executor = get_executor(include_planner=True)
        self.planner = get_planner()

    def ask(
        self,
        question: str,
        drilldown: DrilldownContext | None = None,
        *,
        correlation_id: str | None = None,
    ) -> AgentResult:
        """Главная точка входа через PlannerAgent.

        Возвращает AskResult, DashboardResult или PresentationResult с заполненным trace.
        """
        cid = correlation_id or get_correlation_id() or new_correlation_id()
        start = time.time()
        logger.info(f"[Orchestrator] planner start [{cid}]: question={question[:60]}...")
        run_logger.log_event("ask_start", question=question[:200], correlation_id=cid)

        res = self.planner.run(question, drilldown=drilldown)
        elapsed = int((time.time() - start) * 1000)
        run_logger.log_event(
            "ask_end",
            correlation_id=cid,
            elapsed_ms=elapsed,
            result_type=type(res).__name__,
            success=getattr(res, "success", True),
        )
        logger.info(f"[Orchestrator] planner end [{cid}]: {type(res).__name__} ({elapsed}ms)")
        return res

    def dashboard(
        self,
        question: str,
        max_charts: int = 4,
        include_kpi: bool = True,
        data: list[dict] | None = None,
        drilldown: DrilldownContext | None = None,
        *,
        correlation_id: str | None = None,
    ) -> DashboardResult:
        """Явный fast-path для дашбордов (API / programmatic)."""
        cid = correlation_id or get_correlation_id() or new_correlation_id()
        start = time.time()
        logger.info(f"[Orchestrator] dashboard start [{cid}]: question={question[:60]}...")
        run_logger.log_event("dashboard_start", question=question[:200], correlation_id=cid)

        req = DashboardRequest(
            question=question,
            max_charts=max_charts,
            include_kpi=include_kpi,
            data=data,
            drilldown_filters=drilldown.filters if drilldown else None,
        )
        res = self.executor.run("dashboard_agent", req)
        elapsed = int((time.time() - start) * 1000)
        run_logger.log_event(
            "dashboard_end",
            correlation_id=cid,
            elapsed_ms=elapsed,
            success=getattr(res, "success", True),
        )
        logger.info(
            f"[Orchestrator] dashboard end [{cid}]: charts={len(getattr(res, 'charts', []))} ({elapsed}ms)"
        )
        return res  # type: ignore[return-value]

    def presentation(
        self,
        questions: list[str] | list[dict[str, Any]] | PresentationInput,
        *,
        num_slides: int = 7,
        include_title: bool = True,
        include_recommendations: bool = True,
        correlation_id: str | None = None,
    ) -> PresentationResult:
        """Генерация презентации через PresentationAgent (единый entry point)."""
        cid = correlation_id or get_correlation_id() or new_correlation_id()
        start = time.time()
        logger.info(f"[Orchestrator] presentation start [{cid}]")
        run_logger.log_event("presentation_start", correlation_id=cid)

        res = self.executor.run(
            "presentation_agent",
            questions,
            num_slides=num_slides,
            include_title=include_title,
            include_recommendations=include_recommendations,
        )
        elapsed = int((time.time() - start) * 1000)
        run_logger.log_event(
            "presentation_end",
            correlation_id=cid,
            elapsed_ms=elapsed,
            success=getattr(res, "success", True),
        )
        logger.info(f"[Orchestrator] presentation end [{cid}] ({elapsed}ms)")
        return res  # type: ignore[return-value]

    def ask_result_fallback(self, question: str, res: AgentResult) -> AskResult:
        """Legacy helper: оборачивает не-AskResult в AskResult (для старых UI-путей)."""
        if isinstance(res, AskResult):
            return res
        return AskResult(
            question=question,
            sql=getattr(res, "source_sql", "") or getattr(res, "sql", "") or "",
            data=getattr(res, "data", []) or [],
            reasoning=getattr(res, "reasoning", "PlannerAgent вернул не-AskResult"),
            error=getattr(res, "error", None),
            success=getattr(res, "success", True),
            trace=getattr(res, "trace", None),
        )