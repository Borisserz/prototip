"""Централизованная конфигурация приложения (env + defaults)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Fix for httpx parsing bug with IPv6 localhost in NO_PROXY
for key in ("NO_PROXY", "no_proxy"):
    if key in os.environ:
        os.environ[key] = os.environ[key].replace("::1", "").replace(",,", ",").strip(",")

# Автоматически загружаем .env из корня проекта если он есть.
# Это позволяет запускать сервер без ручного export USE_VERTEX=true и т.д.
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        # python-dotenv не установлен — читаем вручную (fallback)
        with open(_env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


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