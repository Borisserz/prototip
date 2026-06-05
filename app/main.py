"""FastAPI app skeleton for prototip (Phase 0+).

Thin API layer. Business logic lives in orchestrator/agents (later phases).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.schemas import PresentationRequest, PresentationResult

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
    # можно передать настройки, но текущий PresentationAgent использует дефолт; для Phase ок
    return pa.run(questions[: payload.num_slides])
