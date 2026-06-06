"""FastAPI — thin layer над Orchestrator."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.config import config
from app.logging_utils import new_correlation_id
from app.orchestrator import Orchestrator
from app.schemas import (
    DashboardRequest,
    DashboardResult,
    DrilldownContext,
    PresentationRequest,
    PresentationResult,
)

app = FastAPI(
    title="prototip BI",
    version=config.app_version,
    description="Локальная мультиагентная BI-платформа для налоговой аналитики (прототип).",
)

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    drilldown: DrilldownContext | None = None


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "phase": config.app_phase,
        "version": config.app_version,
    }


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "message": "prototip — мультиагентная BI-аналитика (PlannerAgent + Orchestrator)",
        "health": "/health",
        "docs": "/docs",
        "phase": config.app_phase,
    }


@app.post("/ask", tags=["orchestrator"])
def ask_endpoint(payload: AskRequest) -> dict[str, Any]:
    """Универсальный запрос через PlannerAgent."""
    cid = new_correlation_id()
    res = get_orchestrator().ask(
        payload.question,
        drilldown=payload.drilldown,
        correlation_id=cid,
    )
    if hasattr(res, "model_dump"):
        return res.model_dump(mode="json")
    return {"result": str(res), "correlation_id": cid}


@app.post("/generate_dashboard", response_model=DashboardResult, tags=["dashboard"])
def generate_dashboard(payload: DashboardRequest) -> DashboardResult:
    """Явный fast-path дашборда через Orchestrator.dashboard()."""
    cid = new_correlation_id()
    drilldown = None
    if payload.drilldown_filters:
        drilldown = DrilldownContext(filters=payload.drilldown_filters)
    return get_orchestrator().dashboard(
        payload.question,
        max_charts=payload.max_charts,
        include_kpi=payload.include_kpi,
        data=payload.data,
        drilldown=drilldown,
        correlation_id=cid,
    )


@app.post("/generate_presentation", response_model=PresentationResult, tags=["presentation"])
def generate_presentation(payload: PresentationRequest) -> PresentationResult:
    """Генерация презентации через Orchestrator.presentation()."""
    from core.llm import call_structured

    cid = new_correlation_id()
    questions = [q.text for q in payload.questions]
    if payload.mode != "По вопросам" and payload.overall_theme:
        class QList(BaseModel):
            questions: list[str]

        qlist = call_structured(
            f"Разложи тему '{payload.overall_theme}' в 3-5 конкретных вопросов "
            "для презентации по налоговой аналитике РБ (на русском, коротко).",
            schema=QList,
            system="Только список вопросов на русском.",
        )
        questions = qlist.questions

    if not questions:
        questions = ["Структура налогов по видам (доли)"]

    q_for_agent: Any = (
        payload.questions
        if payload.questions and any(getattr(q, "text", "") for q in payload.questions)
        else questions
    )
    return get_orchestrator().presentation(
        q_for_agent,
        num_slides=payload.num_slides,
        include_title=payload.include_title,
        include_recommendations=payload.include_recommendations,
        correlation_id=cid,
    )