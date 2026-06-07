"""Центральный клиент для вызовов локальной LLM (Ollama) со structured output.

Все LLM-вызовы в проекте — ТОЛЬКО через этот модуль (structured JSON по Pydantic, temperature=0).
Модель по умолчанию из env OLLAMA_MODEL или "qwen2.5-coder:7b-instruct".
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TypeVar

import ollama
from pydantic import BaseModel, ValidationError

# Centralized logging setup for Phase 8 (called once on first import of core.llm, which agents use)
_log_configured = False


def setup_logging() -> None:
    """Настроить логгер ОДИН раз: stdout + out/run.log, INFO."""
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
    for noisy in ("kaleido", "urllib3", "httpx", "httpcore", "selenium"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _log_configured = True


setup_logging()

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b-instruct")
LLM_MAX_RETRIES = int(os.getenv("PROTOTIP_LLM_RETRIES", "3"))
LLM_RETRY_DELAY_SEC = float(os.getenv("PROTOTIP_LLM_RETRY_DELAY", "0.8"))

_llm_logger = logging.getLogger("LLM")


def _chat_once(
    *,
    model: str,
    messages: list[dict],
    schema: type[T],
) -> T:
    resp = ollama.chat(
        model=model,
        messages=messages,
        format=schema.model_json_schema(),
        options={"temperature": 0},
    )
    content = resp["message"]["content"]
    return schema.model_validate_json(content)


def call_structured(
    prompt: str,
    schema: type[T],
    model: str | None = None,
    system: str | None = None,
) -> T:
    """Ollama structured output с retry и JSON-repair при ValidationError."""
    mdl = model or DEFAULT_MODEL
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_error: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            return _chat_once(model=mdl, messages=messages, schema=schema)
        except ValidationError as exc:
            last_error = exc
            _llm_logger.info(f"[LLM] validation error attempt {attempt}/{LLM_MAX_RETRIES}: {exc}")
            repair_messages = list(messages)
            repair_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Предыдущий JSON невалиден: {exc}. "
                        "Верни исправленный JSON строго по схеме, без пояснений."
                    ),
                }
            )
            try:
                return _chat_once(model=mdl, messages=repair_messages, schema=schema)
            except Exception as repair_exc:
                last_error = repair_exc
        except Exception as exc:
            last_error = exc
            _llm_logger.info(f"[LLM] call error attempt {attempt}/{LLM_MAX_RETRIES}: {exc}")

        if attempt < LLM_MAX_RETRIES:
            time.sleep(LLM_RETRY_DELAY_SEC * attempt)

    raise RuntimeError(f"LLM structured call failed after {LLM_MAX_RETRIES} attempts: {last_error}")


def is_ollama_available(model: str | None = None) -> bool:
    """Проверка доступности модели (для тестов/живых прогонов)."""
    mdl = model or DEFAULT_MODEL
    try:
        ollama.show(mdl)
        return True
    except Exception:
        return False