"""
WrenAI Client — семантический слой для DataAgent.

get_semantic_context(question) динамически читает:
  1. semantic_rules.json  — бизнес-правила, настроенные через admin-UI
  2. rls_config.yaml      — список разрешённых таблиц и RLS-метаданные
  3. semantic_model.yaml  — MDL-схема таблиц (как дополнительный резерв)

Результат инжектируется в DataAgent._build_prompt() в секции BUSINESS RULES,
тем самым admin-конфигурируемые правила реально влияют на генерацию SQL.

get_rules() / save_rules() — CRUD для semantic_rules.json, используются admin-UI.
sync_schema() — заглушка (реальный WrenAI SDK не используется в этом проекте).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("WrenAIClient")

# Пути к конфигам (относительно этого файла → ../../../data/)
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_RULES_FILE = _DATA_DIR / "semantic_rules.json"
_RLS_CONFIG = Path(__file__).parent.parent.parent / "config" / "rls_config.yaml"
_SEMANTIC_MODEL = _DATA_DIR / "semantic_model.yaml"


class WrenAIClient:
    """
    Семантический слой проекта.

    Не требует внешнего WrenAI-сервиса — работает полностью on-premise:
      • бизнес-правила хранятся в data/semantic_rules.json
      • схема — в data/semantic_model.yaml
      • RLS — в config/rls_config.yaml
    """

    # ------------------------------------------------------------------
    # Бизнес-правила (CRUD, используется admin-UI)
    # ------------------------------------------------------------------

    def get_rules(self) -> list[dict]:
        """Загрузить активные бизнес-правила (admin-UI → semantic_rules.json)."""
        if not _RULES_FILE.exists():
            return [
                {
                    "id": "rule_vip",
                    "name": "VIP Клиент",
                    "description": "Сумма налогов больше 10 млн — признак крупного плательщика",
                    "active": True,
                },
                {
                    "id": "rule_risk",
                    "name": "Высокий риск",
                    "description": "Статус 'Взыскание' или 'Просрочка' означает задолженность",
                    "active": True,
                },
                {
                    "id": "rule_accrued",
                    "name": "Начисления vs Уплата",
                    "description": "Начисления = accrued (tax_data) или amount WHERE status='Оплачено' (enterprise_taxes). Долг = debt или amount WHERE status IN ('Взыскание','Просрочка')",
                    "active": True,
                },
            ]
        try:
            with open(_RULES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error(f"Error loading semantic rules: {exc}")
            return []

    def save_rules(self, rules: list[dict]) -> None:
        """Сохранить бизнес-правила (admin-UI)."""
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(rules)} semantic rules → {_RULES_FILE}")

    # ------------------------------------------------------------------
    # Динамический семантический контекст для DataAgent
    # ------------------------------------------------------------------

    def get_semantic_context(self, question: str) -> str:
        """
        Строит динамический текстовый контекст для LLM-запроса.

        Включает:
          • активные бизнес-правила из semantic_rules.json
          • список таблиц из rls_config.yaml (если доступен)

        Используется DataAgent._build_prompt() → секция BUSINESS RULES.
        """
        logger.info(f"[WrenAI] Building semantic context for: {question[:80]}")

        parts: list[str] = []

        # 1. Бизнес-правила
        rules = [r for r in self.get_rules() if r.get("active", True)]
        if rules:
            parts.append("Активные бизнес-правила (настроены администратором):")
            for r in rules:
                parts.append(f"  • {r['name']}: {r['description']}")

        # 2. Разрешённые таблицы из RLS-конфига
        if _RLS_CONFIG.exists():
            try:
                with open(_RLS_CONFIG, encoding="utf-8") as f:
                    rls = yaml.safe_load(f)
                tables = []
                if isinstance(rls, dict):
                    # структура: {tables: [...]} или {roles: {role: {tables: [...]}}}
                    if "tables" in rls:
                        tables = rls["tables"]
                    elif "roles" in rls:
                        seen: set[str] = set()
                        for role_data in rls["roles"].values():
                            for t in role_data.get("tables") or []:
                                if t not in seen:
                                    tables.append(t)
                                    seen.add(t)
                if tables:
                    parts.append(f"\nДоступные таблицы (RLS): {', '.join(tables)}")
            except Exception as exc:
                logger.warning(f"Could not read rls_config.yaml: {exc}")

        # 3. Краткая подсказка по ключевым колонкам (константа, не меняется)
        parts.append("""
Ключевые маппинги колонок:
  • Начисления налогов: tax_data.accrued ИЛИ enterprise_taxes.amount WHERE status='Оплачено'
  • Задолженность: tax_data.debt ИЛИ enterprise_taxes.amount WHERE status IN ('Взыскание','Просрочка')
  • Регионы РБ: Брестская область, Витебская область, Гомельская область, Гродненская область, Минская область, Могилёвская область, г. Минск
  • Период в tax_data: колонка period (Date); в enterprise_taxes: date (Date)
""")

        return "\n".join(parts) if parts else "Бизнес-правила не настроены."

    # ------------------------------------------------------------------
    # Служебное
    # ------------------------------------------------------------------

    def sync_schema(self, schema_def: dict[str, Any]) -> bool:
        """
        Синхронизация схемы (stub — реальный WrenAI SDK не используется).
        Логирует схему для отладки.
        """
        logger.info(
            f"[WrenAI] sync_schema called with {len(schema_def)} keys — "
            "no external service, operation skipped (on-premise mode)"
        )
        return True


wren_client = WrenAIClient()
