"""Structured run logging с correlation_id для трассировки запросов."""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from datetime import timezone, datetime
from pathlib import Path
from typing import Any

from app.config import config

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    """Создаёт и устанавливает correlation_id для текущего контекста."""
    cid = uuid.uuid4().hex[:12]
    correlation_id_var.set(cid)
    return cid


def get_correlation_id() -> str:
    return correlation_id_var.get() or ""


def set_correlation_id(correlation_id: str) -> str:
    """Устанавливает correlation_id для текущего контекста (оркестратор / API)."""
    correlation_id_var.set(correlation_id)
    return correlation_id


class JsonRunLogger:
    """Append-only JSONL лог прогонов в out/runs/."""

    def __init__(self, out_dir: Path | None = None) -> None:
        self.out_dir = out_dir or (config.out_dir / "runs")
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def log_event(self, event: str, **payload: Any) -> None:
        cid = get_correlation_id() or "unknown"
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "correlation_id": cid,
            "event": event,
            **payload,
        }
        path = self.out_dir / f"run_{cid}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


run_logger = JsonRunLogger()
