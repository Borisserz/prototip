"""FastAPI app skeleton for prototip (Phase 0+).

Thin API layer. Business logic lives in orchestrator/agents (later phases).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.schemas import DashboardRequest, DashboardResult, PresentationRequest, PresentationResult

app = FastAPI(
    title="prototip BI",
    version="0.1.0",
    description="Локальная мультиагентная BI-платформа для налоговой аналитики (прототип).",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Health check endpoint.

    Returns basic status. Used to verify Phase 0 skeleton is running.
    """
    return {"status": "ok", "phase": "0"}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    """Root endpoint (informational)."""
    return {
        "message": "prototip — Text-to-SQL + красивые графики (Phase 0 каркас готов)",
        "health": "/health",
        "docs": "/docs",
    }


@app.post("/generate_presentation", response_model=PresentationResult, tags=["presentation"])
def generate_presentation(payload: PresentationRequest) -> PresentationResult:
    """Генерация презентации по структурированному payload из формы UI.
    Thin: основная логика в PresentationAgent (и LLM structured для free mode).
    """
    from app.agents.presentation_agent import PresentationAgent
    from core.llm import call_structured

    # Для free_topic / one_sentence — разложить в список вопросов через structured LLM
    questions = [q.text for q in payload.questions]
    if payload.mode != "По вопросам" and payload.overall_theme:
        # structured expand
        expand_prompt = f"Разложи тему '{payload.overall_theme}' в 3-5 конкретных вопросов для презентации по налоговой аналитике РБ (на русском, коротко)."
        # простая схема для списка
        from pydantic import BaseModel

        class QList(BaseModel):
            questions: list[str]

        qlist = call_structured(
            expand_prompt, schema=QList, system="Только список вопросов на русском."
        )
        questions = qlist.questions

    if not questions:
        questions = ["Структура налогов по видам (доли)"]  # fallback

    pa = PresentationAgent()
    # Передаём полный payload (вопросы с prefs + настройки) — агент сам сделает exact count + respect includes/prefs
    # Для free/expand используем list[str] если нет блоков; run поддерживает оба
    q_for_agent = (
        payload.questions
        if payload.questions and any(getattr(q, "text", "") for q in payload.questions)
        else questions
    )
    return pa.run(
        q_for_agent,
        num_slides=payload.num_slides,
        include_title=payload.include_title,
        include_recommendations=payload.include_recommendations,
    )


@app.post("/generate_dashboard", response_model=DashboardResult, tags=["dashboard"])
def generate_dashboard(payload: DashboardRequest) -> DashboardResult:
    """Генерация дашборда (KPI + несколько ChartSpec + layout + insights) по одному вопросу.
    Thin: логика в DashboardAgent (с reuse Data/Analyst/Chart).
    """
    from app.agents.dashboard_agent import DashboardAgent

    da = DashboardAgent()
    return da.run(payload)
