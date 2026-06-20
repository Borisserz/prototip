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

# ollama is imported lazily inside _chat_once() to avoid startup crash
# when OLLAMA_HOST env var is misconfigured but USE_VERTEX=true is set.
from pydantic import BaseModel, ValidationError

# Centralized logging setup for Phase 8 (called once on first import of core.llm, which agents use)
_log_configured = False


def setup_logging() -> None:
    """Настроить логгер ОДИН раз: stdout + out/run.log, INFO (Structured JSON Phase 19)."""
    global _log_configured
    if _log_configured:
        return
    root = logging.getLogger()
    if root.handlers:
        _log_configured = True
        return
    log_dir = Path("out")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        from pythonjsonlogger import jsonlogger
        formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    except ImportError:
        formatter = logging.Formatter("%(asctime)s %(message)s")
        
    file_handler = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, stream_handler],
    )
    for noisy in ("kaleido", "urllib3", "httpx", "httpcore", "selenium"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _log_configured = True


setup_logging()

# Phase 8: бизнес-метрики Prometheus (импорт защищён — не должен ломать LLM-слой)
try:
    from app.observability.metrics import observe_llm_call
except Exception:  # pragma: no cover
    def observe_llm_call(**_kwargs):  # type: ignore
        return None

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
    agent_name: str = "unknown"
) -> T:
    use_vertex = os.getenv("USE_VERTEX", "").lower() == "true"

    if use_vertex:
        from google import genai
        from google.genai import types
        import time
        import json
        
        # Extract system instruction
        system_instruction = None
        genai_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = content
            else:
                genai_role = "user" if role == "user" else "model"
                genai_messages.append(types.Content(role=genai_role, parts=[types.Part.from_text(text=content)]))
        
        # Resolve project ID from credentials if possible
        project_id = None
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            try:
                with open(creds_path, "r") as f:
                    project_id = json.load(f).get("project_id")
            except Exception:
                pass
                
        client = genai.Client(vertexai=True, project=project_id, location="global")
        vertex_model = os.getenv("AI_MODEL", "gemini-3.5-flash")
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
            system_instruction=system_instruction
        )
        
        start_time = time.time()
        resp = client.models.generate_content(
            model=vertex_model,
            contents=genai_messages,
            config=config
        )
        duration_ms = int((time.time() - start_time) * 1000)
        
        try:
            prompt_tokens = resp.usage_metadata.prompt_token_count if resp.usage_metadata else 0
            completion_tokens = resp.usage_metadata.candidates_token_count if resp.usage_metadata else 0
        except Exception:
            prompt_tokens = 0
            completion_tokens = 0
            
        try:
            from app.utils.system_logger import audit_logger
            from app.agent_context import get_user_role
            user_role = get_user_role() if get_user_role else "system"
            audit_logger.log_llm_call_async(
                agent_name=agent_name,
                model=vertex_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=duration_ms,
                error_status="",
                user_role=user_role
            )
        except Exception as e:
            _llm_logger.warning(f"Failed to log LLM metrics: {e}")

        observe_llm_call(
            agent=agent_name,
            model=vertex_model,
            status="ok",
            duration_s=duration_ms / 1000.0,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return schema.model_validate_json(resp.text)

    else:
        import ollama  # lazy import — only when USE_VERTEX=false
        resp = ollama.chat(
            model=model,
            messages=messages,
            format=schema.model_json_schema(),
            options={"temperature": 0},
        )
        content = resp["message"]["content"]
        
        try:
            prompt_tokens = resp.get("prompt_eval_count", 0)
            completion_tokens = resp.get("eval_count", 0)
            duration_ns = resp.get("eval_duration", 0) + resp.get("prompt_eval_duration", 0)
            duration_ms = duration_ns // 1000000
        except Exception:
            prompt_tokens = 0
            completion_tokens = 0
            duration_ms = 0
            
    # Логируем в ClickHouse
    try:
        from app.utils.system_logger import audit_logger
        from app.agent_context import get_user_role
        user_role = get_user_role() if get_user_role else "system"
        
        audit_logger.log_llm_call_async(
            agent_name=agent_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            error_status="",
            user_role=user_role
        )
    except Exception as e:
        _llm_logger.warning(f"Failed to log LLM metrics: {e}")

    observe_llm_call(
        agent=agent_name,
        model=model,
        status="ok",
        duration_s=duration_ms / 1000.0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    return schema.model_validate_json(content)


def call_structured(
    prompt: str,
    schema: type[T],
    model: str | None = None,
    system: str | None = None,
    agent_name: str = "unknown"
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
            return _chat_once(model=mdl, messages=messages, schema=schema, agent_name=agent_name)
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
                return _chat_once(model=mdl, messages=repair_messages, schema=schema, agent_name=agent_name)
            except Exception as repair_exc:
                last_error = repair_exc
        except Exception as exc:
            last_error = exc
            _llm_logger.info(f"[LLM] call error attempt {attempt}/{LLM_MAX_RETRIES}: {exc}")

        if attempt < LLM_MAX_RETRIES:
            time.sleep(LLM_RETRY_DELAY_SEC * attempt)

    observe_llm_call(agent=agent_name, model=mdl, status="error", duration_s=0.0)
    raise RuntimeError(f"LLM structured call failed after {LLM_MAX_RETRIES} attempts: {last_error}")


def is_ollama_available(model: str | None = None) -> bool:
    """Проверка доступности модели (для тестов/живых прогонов)."""
    mdl = model or DEFAULT_MODEL
    try:
        import ollama  # lazy import
        ollama.show(mdl)
        return True
    except Exception:
        return False