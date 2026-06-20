"""Orchestrator: единая точка входа ask / dashboard / presentation.

ask() делегирует PlannerAgent (singleton, shared executor).
dashboard() и presentation() — прямые вызовы через AgentExecutor.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.agents.factory import get_executor
from app.agents.models import AgentResult
from app.config import config
from app.logging_utils import get_correlation_id, new_correlation_id, run_logger, set_correlation_id
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
        self.executor = get_executor(include_planner=False)

    def ask(
        self,
        question: str,
        drilldown: DrilldownContext | None = None,
        *,
        correlation_id: str | None = None,
        user: dict | None = None,
        session_id: str | None = None,
    ) -> AgentResult:
        """Главная точка входа через PlannerAgent.

        Возвращает AskResult, DashboardResult или PresentationResult с заполненным trace.
        """
        cid = correlation_id or get_correlation_id() or new_correlation_id()
        set_correlation_id(cid)
        start = time.time()
        logger.info(f"[Orchestrator] planner start [{cid}]: question={question[:60]}...")
        run_logger.log_event("ask_start", question=question[:200], correlation_id=cid)

        import uuid

        from app.agent_context import user_context
        from app.graph import graph
        from app.utils.memory import conversation_memory
        
        session_id = session_id or "default_session"
        conversation_memory.add_message(session_id, "user", question)
        
        # CRITICAL FIX: Use a unique thread_id per invocation.
        # LangGraph MemorySaver checkpoints state per thread_id. If we reuse
        # "default_session" as thread_id, every new request (including drill-downs)
        # would resume from the previous run's stale checkpoint, causing drill-down
        # to always return the previous response.
        # Using a unique UUID ensures every invocation runs from a clean state.
        graph_thread_id = str(uuid.uuid4())
        
        user_role = user.get("role", "manager") if user else "manager"
        user_id = (user.get("username") or user.get("id")) if user else None

        # Phase 6: разрешаем клиента (tenant) по claim client_id из JWT
        client_id = user.get("client_id") if user else None
        from app.agent_context import tenant_context
        from core.tenant import tenant_store
        tenant = tenant_store.get_tenant(client_id) if client_id else None
        if tenant is not None:
            logger.info(f"[Orchestrator] Запрос в контексте клиента '{tenant.client_id}'")

        with user_context(user_role), tenant_context(tenant):
            # Запуск графа LangGraph
            config_data = {"configurable": {"thread_id": graph_thread_id}}
            initial_state = {
                "question": question,
                "drilldown": drilldown,
                "user_role": user_role,
                "user_id": user_id,
                "messages": [],
                "tasks_completed": [],
                "agent_results": {}
            }
            
            # Получаем финальный стейт
            final_state = graph.invoke(initial_state, config=config_data)
            res = final_state.get("final_result", AskResult(question=question, success=False, error="Graph execution failed"))
        
        elapsed = int((time.time() - start) * 1000)
        
        brief = getattr(res, "reasoning", "...") if hasattr(res, "reasoning") else "Выполнено через LangGraph"
        import re
        if not re.sub(r'```json.*?```', '', brief, flags=re.DOTALL).strip():
            fallback = getattr(res, "answer", "Анализ данных завершен.")
            brief = f"{fallback}\n\n{brief}"
        
        conversation_memory.add_message(
            session_id, 
            "bot", 
            brief,
            sql=getattr(res, "sql", ""),
            excel_path=getattr(res, "excel_path", ""),
            pptx_path=getattr(res, "pptx_path", "")
        )

        # Phase 4: запись в долгосрочную память (профиль/RAG по истории).
        # Внутри полностью защищено try/except — не влияет на ответ пользователю.
        try:
            from core.memory_store import memory_store
            memory_store.log_interaction(user_id, question, brief)
        except Exception as mem_err:  # noqa: BLE001
            logger.warning(f"[Orchestrator] memory log skipped: {mem_err}")
        
        run_logger.log_event(
            "ask_end",
            correlation_id=cid,
            elapsed_ms=elapsed,
            result_type=type(res).__name__,
            success=getattr(res, "success", True),
        )
        logger.info(f"[Orchestrator] planner end [{cid}]: {type(res).__name__} ({elapsed}ms)")
        return res

    async def ask_stream(
        self,
        question: str,
        drilldown: Optional[DrilldownContext] = None,
        correlation_id: Optional[str] = None,
        user: Optional[dict] = None,
    ):
        """Async stream for SSE."""
        import json

        from app.graph import graph
        
        correlation_id or get_correlation_id() or new_correlation_id()
        initial_state = {
            "question": question,
            "drilldown": drilldown,
            "user_role": user.get("role", "manager") if user else "manager",
            "user_id": (user.get("username") or user.get("id")) if user else None,
            "messages": [],
        }
        
        try:
            # LangGraph v2 streaming events
            async for event in graph.astream_events(initial_state, config=config, version="v2"):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        yield f"data: {json.dumps({'type': 'text', 'content': chunk.content}, ensure_ascii=False)}\\n\\n"
                        
            # Final completion event
            yield f"data: {json.dumps({'type': 'done', 'content': ''})}\\n\\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\\n\\n"

    def dashboard(
        self,
        question: str,
        max_charts: int = 4,
        include_kpi: bool = True,
        data: list[dict] | None = None,
        drilldown: DrilldownContext | None = None,
        *,
        correlation_id: str | None = None,
        session_id: str | None = None,
    ) -> DashboardResult:
        """Явный fast-path для дашбордов (API / programmatic)."""
        cid = correlation_id or get_correlation_id() or new_correlation_id()
        set_correlation_id(cid)
        start = time.time()
        logger.info(f"[Orchestrator] dashboard start [{cid}]: question={question[:60]}...")
        run_logger.log_event("dashboard_start", question=question[:200], correlation_id=cid)


        from app.pipeline_progress import pipeline_store
        pipeline_store.reset(run_id=cid, question=question)

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
        pipeline_store.finish(success=getattr(res, "success", True), error=getattr(res, "error", None))
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
        set_correlation_id(cid)
        start = time.time()
        logger.info(f"[Orchestrator] presentation start [{cid}]")
        run_logger.log_event("presentation_start", correlation_id=cid)

        from app.pipeline_progress import pipeline_store
        q_str = str(questions) if isinstance(questions, list) else questions.overall_theme or "Презентация"
        pipeline_store.reset(run_id=cid, question=q_str)

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
        pipeline_store.finish(success=getattr(res, "success", True), error=getattr(res, "error", None))
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