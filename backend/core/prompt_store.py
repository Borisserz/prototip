"""Центр управления промптами.

Единый парсер YAML-конфигурации агентов (`app/config/agents.yaml`) в `core/`:
  - динамическая подгрузка с hot-reload по mtime (промпты применяются без рестарта);
  - чтение всех/одного агента + сырого YAML;
  - безопасное обновление одного агента или всего файла с валидацией схемы;
  - синглтон `prompt_store` для импорта из API-слоя и графа.

Совместим с `app/agents/config_loader.py` (тот тоже hot-reload'ит этот же файл),
поэтому запись через Модуль автоматически подхватывается агентами при
следующем обращении — без перезапуска процесса.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("PromptStore")

REQUIRED_FIELDS = ("role", "goal", "rules")
OPTIONAL_FIELDS = ("few_shot",)


class PromptConfig(BaseModel):
    role: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    rules: str = Field(..., min_length=1)
    few_shot: str = Field("")


def _default_path() -> str:
    # core/ -> корень проекта -> app/config/agents.yaml
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "app", "config", "agents.yaml")


class PromptStore:
    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = config_path or _default_path()
        self._cache: dict[str, Any] = {}
        self._last_mtime = 0.0
        self._lock = threading.RLock()

    # ── чтение ──────────────────────────────────────────────────────────────
    def load_all(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Config not found: {self.config_path}")
            mtime = os.path.getmtime(self.config_path)
            if force or mtime > self._last_mtime or not self._cache:
                with open(self.config_path, encoding="utf-8") as f:
                    self._cache = yaml.safe_load(f) or {}
                self._last_mtime = mtime
                logger.info(
                    "PromptStore: перечитан %s (%d агентов)", self.config_path, len(self._cache)
                )
            return self._cache

    def reload(self) -> dict[str, Any]:
        return self.load_all(force=True)

    def list_agents(self) -> list[str]:
        return list(self.load_all().keys())

    def get_agent(self, name: str) -> dict[str, Any]:
        cfg = self.load_all()
        if name not in cfg:
            raise KeyError(f"Агент '{name}' не найден")
        return dict(cfg[name])

    def get_raw(self) -> str:
        with open(self.config_path, encoding="utf-8") as f:
            return f.read()

    # ── запись ──────────────────────────────────────────────────────────────
    def _atomic_write(self, data: dict[str, Any]) -> None:
        tmp = f"{self.config_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        os.replace(tmp, self.config_path)
        self.reload()

    def update_agent(self, name: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Обновляет/создаёт конфигурацию одного агента. Валидирует схему."""
        with self._lock:
            cfg = dict(self.load_all())
            merged = {**cfg.get(name, {}), **fields}
            try:
                validated = PromptConfig(**merged).model_dump()
            except ValidationError as e:
                raise ValueError(f"Невалидная конфигурация агента '{name}': {e}") from e
            cfg[name] = validated
            self._atomic_write(cfg)
            logger.info("PromptStore: обновлён агент '%s'", name)
            return validated

    def set_raw(self, raw_yaml: str) -> dict[str, Any]:
        """Заменяет весь YAML целиком с валидацией всех агентов."""
        with self._lock:
            try:
                parsed = yaml.safe_load(raw_yaml)
            except yaml.YAMLError as e:
                raise ValueError(f"Ошибка парсинга YAML: {e}") from e
            if not isinstance(parsed, dict) or not parsed:
                raise ValueError("YAML должен содержать словарь агентов")
            errors: list[str] = []
            for name, body in parsed.items():
                if not isinstance(body, dict):
                    errors.append(f"'{name}': ожидается объект")
                    continue
                try:
                    PromptConfig(**body)
                except ValidationError as e:
                    errors.append(f"'{name}': {e.errors()[0]['msg']} ({e.errors()[0]['loc']})")
            if errors:
                raise ValueError("Ошибки валидации: " + "; ".join(errors))
            self._atomic_write(parsed)
            logger.info("PromptStore: заменён весь YAML (%d агентов)", len(parsed))
            return parsed

    def delete_agent(self, name: str) -> None:
        with self._lock:
            cfg = dict(self.load_all())
            if name not in cfg:
                raise KeyError(f"Агент '{name}' не найден")
            del cfg[name]
            self._atomic_write(cfg)
            logger.info("PromptStore: удалён агент '%s'", name)


# Глобальный синглтон
prompt_store = PromptStore()
