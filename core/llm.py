"""Центральный клиент для вызовов локальной LLM (Ollama) со structured output.

Все LLM-вызовы в проекте — ТОЛЬКО через этот модуль (structured JSON по Pydantic, temperature=0).
Модель по умолчанию из env OLLAMA_MODEL или "qwen2.5-coder:7b-instruct".
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TypeVar

import ollama
from pydantic import BaseModel

# Centralized logging setup for Phase 8 (called once on first import of core.llm, which agents use)
_log_configured = False


def setup_logging() -> None:
    """Настроить логгер ОДИН раз: stdout + out/run.log, INFO.

    Формат логов: [AgentName] action: details (Nms)
    Все агенты используют getLogger("Name") и пишут сообщения начиная с [Name].
    """
    global _log_configured
    if _log_configured:
        return
    root = logging.getLogger()
    if root.handlers:
        _log_configured = True
        return
    log_dir = Path("out")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "run.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    # Suppress noisy third-party INFO logs (kaleido etc) so only our [Agent] lines are prominent
    for noisy in ("kaleido", "urllib3", "httpx", "httpcore", "selenium"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _log_configured = True


# Ensure configured when llm (and thus agents) imported
setup_logging()

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b-instruct")


def call_structured(
    prompt: str,
    schema: type[T],
    model: str | None = None,
    system: str | None = None,
) -> T:
    """Вызывает Ollama с format=JSON schema из Pydantic и возвращает валидный экземпляр.

    temperature=0 для детерминизма (SQL/ChartSpec).
    """
    mdl = model or DEFAULT_MODEL
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = ollama.chat(
        model=mdl,
        messages=messages,
        format=schema.model_json_schema(),
        options={"temperature": 0},
    )
    content = resp["message"]["content"]
    return schema.model_validate_json(content)


def is_ollama_available(model: str | None = None) -> bool:
    """Проверка доступности модели (для тестов/живых прогонов)."""
    mdl = model or DEFAULT_MODEL
    try:
        ollama.show(mdl)
        return True
    except Exception:
        return False
