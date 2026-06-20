"""Долгосрочная память пользователя (Phase 4): профили + RAG по истории чата.

Архитектурно повторяет существующий RAG (app/services/rag_service.py): хранилище —
ClickHouse, эмбеддинги — all-MiniLM-L6-v2 (с fallback на FakeEmbeddings), поиск —
cosineDistance. Никакого нового сервиса в docker-compose не требуется: ClickHouse и
модель эмбеддингов уже есть.

Две таблицы:
  • user_profiles      — текстовое описание пользователя (кто он, чем занимается).
  • chat_history_logs  — журнал (user_id, prompt, response, ts) + эмбеддинг prompt
                         для семантического поиска по прошлым запросам.

Memory Node графа перед генерацией SQL делает RAG-поиск по запросам пользователя за
последнюю неделю и обогащает System Prompt («Пользователь — бухгалтер, недавно искал
данные по налогам за май»).

ВАЖНО: весь модуль максимально устойчив — любая ошибка памяти (нет ClickHouse, нет
модели и т.п.) логируется и проглатывается, чтобы НИКОГДА не ломать основной поток.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

logger = logging.getLogger("MemoryStore")

# Настройки (тюнятся через env / docker-compose)
MEMORY_RAG_DAYS = int(os.getenv("MEMORY_RAG_DAYS", "7"))
MEMORY_RAG_TOPK = int(os.getenv("MEMORY_RAG_TOPK", "5"))
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() in ("1", "true", "yes")


def _esc(value: str) -> str:
    """Экранирование строки для безопасной вставки в SQL-литерал ClickHouse."""
    return str(value).replace("\\", "\\\\").replace("'", "''")


class MemoryStore:
    """Долгосрочная память: профили пользователей + журнал/RAG истории чата."""

    def __init__(self) -> None:
        self._tables_ready = False
        self._embeddings = None

    # ─── инфраструктура ──────────────────────────────────────────────────────
    def _client(self):
        from app.utils.clickhouse_client import ch_client

        return ch_client

    def _embed(self, text: str) -> list[float] | None:
        """Эмбеддинг текста той же моделью, что и основной RAG."""
        try:
            if self._embeddings is None:
                from app.services.rag_service import get_embeddings_model

                self._embeddings = get_embeddings_model()
            return self._embeddings.embed_query(text or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryStore: эмбеддинг недоступен: %s", e)
            return None

    def init_tables(self) -> None:
        """Идемпотентно создаёт таблицы памяти (CREATE IF NOT EXISTS)."""
        if self._tables_ready:
            return
        try:
            ch = self._client()
            ch.command(
                """
                CREATE TABLE IF NOT EXISTS default.user_profiles (
                    user_id    String,
                    profile    String,
                    role       String DEFAULT '',
                    updated_at DateTime DEFAULT now()
                ) ENGINE = ReplacingMergeTree(updated_at)
                ORDER BY user_id
                """
            )
            ch.command(
                """
                CREATE TABLE IF NOT EXISTS default.chat_history_logs (
                    id        String,
                    user_id   String,
                    prompt    String,
                    response  String,
                    ts        DateTime DEFAULT now(),
                    embedding Array(Float32)
                ) ENGINE = MergeTree()
                ORDER BY (user_id, ts)
                """
            )
            self._tables_ready = True
            logger.info("MemoryStore: таблицы user_profiles / chat_history_logs готовы.")
        except Exception as e:  # noqa: BLE001
            logger.error("MemoryStore: не удалось создать таблицы: %s", e)

    # ─── запись истории ──────────────────────────────────────────────────────
    def log_interaction(self, user_id: str | None, prompt: str, response: str) -> None:
        """Сохраняет пару (запрос, ответ) пользователя + эмбеддинг запроса."""
        if not MEMORY_ENABLED or not user_id:
            return
        try:
            self.init_tables()
            emb = self._embed(prompt) or []
            ch = self._client()
            ch.insert(
                "chat_history_logs",
                [[
                    uuid.uuid4().hex,
                    str(user_id),
                    (prompt or "")[:8000],
                    (response or "")[:8000],
                    datetime.now(UTC).replace(tzinfo=None),
                    emb,
                ]],
                column_names=["id", "user_id", "prompt", "response", "ts", "embedding"],
            )
        except Exception as e:  # noqa: BLE001
            logger.error("MemoryStore.log_interaction: %s", e)

    # ─── RAG-поиск по прошлым запросам ───────────────────────────────────────
    def search_recent(
        self,
        user_id: str,
        query: str,
        days: int | None = None,
        k: int | None = None,
    ) -> list[dict]:
        """Семантический поиск похожих запросов пользователя за последние `days` дней."""
        if not MEMORY_ENABLED or not user_id:
            return []
        days = days or MEMORY_RAG_DAYS
        k = k or MEMORY_RAG_TOPK
        try:
            self.init_tables()
            vec = self._embed(query)
            ch = self._client()
            if vec:
                sql = f"""
                SELECT prompt, response, ts, cosineDistance(embedding, {vec}) AS dist
                FROM default.chat_history_logs
                WHERE user_id = '{_esc(user_id)}'
                  AND ts >= now() - INTERVAL {int(days)} DAY
                  AND length(embedding) > 0
                ORDER BY dist ASC
                LIMIT {int(k)}
                """
            else:
                # fallback без эмбеддингов — просто последние запросы за период
                sql = f"""
                SELECT prompt, response, ts, 0 AS dist
                FROM default.chat_history_logs
                WHERE user_id = '{_esc(user_id)}'
                  AND ts >= now() - INTERVAL {int(days)} DAY
                ORDER BY ts DESC
                LIMIT {int(k)}
                """
            rows = ch.get_client().query(sql).result_rows
            return [
                {"prompt": r[0], "response": r[1], "ts": r[2], "dist": float(r[3])}
                for r in rows
            ]
        except Exception as e:  # noqa: BLE001
            logger.error("MemoryStore.search_recent: %s", e)
            return []

    # ─── профили ─────────────────────────────────────────────────────────────
    def get_profile(self, user_id: str) -> dict | None:
        if not user_id:
            return None
        try:
            self.init_tables()
            ch = self._client()
            sql = f"""
            SELECT profile, role, updated_at
            FROM default.user_profiles FINAL
            WHERE user_id = '{_esc(user_id)}'
            LIMIT 1
            """
            rows = ch.get_client().query(sql).result_rows
            if not rows:
                return None
            return {
                "user_id": user_id,
                "profile": rows[0][0],
                "role": rows[0][1],
                "updated_at": rows[0][2],
            }
        except Exception as e:  # noqa: BLE001
            logger.error("MemoryStore.get_profile: %s", e)
            return None

    def upsert_profile(self, user_id: str, profile: str, role: str = "") -> bool:
        if not user_id:
            return False
        try:
            self.init_tables()
            ch = self._client()
            ch.insert(
                "user_profiles",
                [[str(user_id), profile or "", role or "", datetime.now(UTC).replace(tzinfo=None)]],
                column_names=["user_id", "profile", "role", "updated_at"],
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("MemoryStore.upsert_profile: %s", e)
            return False

    def recent_history(self, user_id: str, limit: int = 20) -> list[dict]:
        """Хронологическая лента истории (для UI/админки)."""
        if not user_id:
            return []
        try:
            self.init_tables()
            ch = self._client()
            sql = f"""
            SELECT prompt, response, ts
            FROM default.chat_history_logs
            WHERE user_id = '{_esc(user_id)}'
            ORDER BY ts DESC
            LIMIT {int(limit)}
            """
            rows = ch.get_client().query(sql).result_rows
            return [{"prompt": r[0], "response": r[1], "ts": str(r[2])} for r in rows]
        except Exception as e:  # noqa: BLE001
            logger.error("MemoryStore.recent_history: %s", e)
            return []

    # ─── сборка контекста для System Prompt ──────────────────────────────────
    def build_memory_context(
        self,
        user_id: str | None,
        question: str,
        days: int | None = None,
        k: int | None = None,
    ) -> str:
        """Готовый фрагмент System Prompt: профиль + релевантные прошлые запросы.

        Возвращает пустую строку, если памяти нет — это безопасно для графа.
        """
        if not MEMORY_ENABLED or not user_id:
            return ""

        parts: list[str] = []

        profile = self.get_profile(user_id)
        if profile and (profile.get("profile") or "").strip():
            role = f" (роль: {profile['role']})" if profile.get("role") else ""
            parts.append(f"Профиль пользователя{role}: {profile['profile'].strip()}")

        hits = self.search_recent(user_id, question, days=days, k=k)
        # отбрасываем точный повтор текущего вопроса
        seen: set[str] = set()
        recent_lines: list[str] = []
        for h in hits:
            p = (h.get("prompt") or "").strip()
            if not p or p == (question or "").strip() or p in seen:
                continue
            seen.add(p)
            ts = h.get("ts")
            when = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
            recent_lines.append(f"  • [{when}] {p[:160]}")

        if recent_lines:
            parts.append(
                "Недавние запросы пользователя за последнюю неделю "
                "(используй как контекст, если уместно):\n" + "\n".join(recent_lines)
            )

        if not parts:
            return ""

        return (
            "=== Долгосрочная память о пользователе ===\n"
            + "\n".join(parts)
            + "\n=========================================="
        )


# Глобальный singleton
memory_store = MemoryStore()
