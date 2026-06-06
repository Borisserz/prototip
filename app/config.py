"""Централизованная конфигурация приложения (env + defaults)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AppConfig:
    """Настройки прототипа; переопределяются через переменные окружения PROTOTIP_*."""

    ollama_model: str = os.getenv("PROTOTIP_OLLAMA_MODEL", "qwen2.5-coder:7b-instruct")
    pipeline_timeout_sec: int = int(os.getenv("PROTOTIP_PIPELINE_TIMEOUT", "600"))
    planner_cache_size: int = int(os.getenv("PROTOTIP_PLANNER_CACHE_SIZE", "32"))
    data_path: Path = Path(os.getenv("PROTOTIP_DATA_PATH", str(PROJECT_ROOT / "data" / "sample.csv")))
    out_dir: Path = Path(os.getenv("PROTOTIP_OUT_DIR", "out"))
    app_phase: str = os.getenv("PROTOTIP_PHASE", "8")
    app_version: str = os.getenv("PROTOTIP_VERSION", "0.8.0")


config = AppConfig()