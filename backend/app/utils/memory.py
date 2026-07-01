"""Хранилище контекста диалога с поддержкой изоляции по user_id.

Структура файла sessions.json:
  {
    "<user_id>": {
      "<session_id>": [{"role": ..., "text": ..., "timestamp": ...}, ...]
    }
  }

Изоляция: каждый пользователь видит только свои сессии.
Для анонимных/системных вызовов используется user_id=ANONYMOUS.

MIGRATION: при загрузке старого формата {session_id: [msgs]} данные
переносятся в пространство ANONYMOUS для обратной совместимости.
"""

import json
import logging
import os
import threading
import time

logger = logging.getLogger("Memory")

ANONYMOUS = "anonymous"


class ConversationMemory:
    """Хранилище контекста диалога с персистентностью в JSON.

    Изолировано по user_id — пользователь видит только свои сессии.
    """

    def __init__(self):
        # {user_id: {session_id: [msgs]}}
        self._data: dict[str, dict[str, list]] = {}
        self._lock = threading.RLock()
        self.file_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "sessions.json"
        )
        self.ttl_seconds = 86400  # 24 часа
        self._load()

    # Персистентность

    def _load(self):
        with self._lock:
            if not os.path.exists(self.file_path):
                return
            try:
                with open(self.file_path, encoding="utf-8") as f:
                    raw = json.load(f)
                # Миграция: старый формат — {session_id: [msgs]}
                # Новый формат — {user_id: {session_id: [msgs]}}
                if raw and isinstance(next(iter(raw.values()), None), list):
                    self._data = {ANONYMOUS: raw}
                    logger.info("[Memory] Мигрирован legacy sessions.json → anonymous namespace")
                else:
                    self._data = raw
            except Exception as e:
                logger.error(f"[Memory] Не удалось загрузить sessions.json: {e}")

    def _save(self):
        with self._lock:
            try:
                now = time.time()
                # TTL-очистка по всем пользователям
                for uid in list(self._data.keys()):
                    user_sessions = self._data[uid]
                    for sid in list(user_sessions.keys()):
                        msgs = user_sessions[sid]
                        if not msgs or now - msgs[-1].get("timestamp", now) > self.ttl_seconds:
                            del user_sessions[sid]
                    if not user_sessions:
                        del self._data[uid]

                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                tmp_path = self.file_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.file_path)
            except Exception as e:
                logger.error(f"[Memory] Не удалось сохранить sessions: {e}")


    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        user_id: str | None = None,
        **kwargs,
    ):
        """Добавить сообщение в сессию пользователя."""
        if not session_id:
            return
        uid = (user_id or ANONYMOUS).strip() or ANONYMOUS
        with self._lock:
            if uid not in self._data:
                self._data[uid] = {}
            if session_id not in self._data[uid]:
                self._data[uid][session_id] = []
            msg_data = {"role": role, "text": text}
            msg_data["timestamp"] = kwargs.pop("timestamp", time.time())
            msg_data.update(kwargs)
            self._data[uid][session_id].append(msg_data)
            self._save()

    def get_context_string(self, session_id: str, user_id: str | None = None) -> str:
        """Строка контекста диалога (последние 6 сообщений) — только для user_id."""
        uid = (user_id or ANONYMOUS).strip() or ANONYMOUS
        with self._lock:
            if not session_id:
                return ""
            # Ищем в пространстве пользователя, затем — в anonymous (fallback)
            msgs = (
                self._data.get(uid, {}).get(session_id)
                or self._data.get(ANONYMOUS, {}).get(session_id)
                or []
            )
            if not msgs:
                return ""
            lines = []
            for msg in msgs[-6:]:
                r_name = "Пользователь" if msg["role"] == "user" else "Система"
                txt = msg["text"][:300] + ("..." if len(msg["text"]) > 300 else "")
                lines.append(f"{r_name}: {txt}")
            return "История диалога:\n" + "\n".join(lines) + "\n"

    def get_user_sessions(self, user_id: str | None = None) -> dict[str, list]:
        """Все сессии конкретного пользователя (для пользовательского API).

        Возвращает только сессии user_id — никаких чужих данных.
        """
        self._load()
        uid = (user_id or ANONYMOUS).strip() or ANONYMOUS
        with self._lock:
            return dict(self._data.get(uid, {}))

    def get_session(self, session_id: str, user_id: str | None = None) -> list | None:
        """Сообщения сессии — только если она принадлежит user_id."""
        self._load()
        uid = (user_id or ANONYMOUS).strip() or ANONYMOUS
        with self._lock:
            return self._data.get(uid, {}).get(session_id)

    def get_all_sessions(self) -> dict:
        """[ADMIN ONLY] Плоский dict {session_id: msgs} по всем пользователям.

        НЕ ИСПОЛЬЗОВАТЬ в пользовательских API-маршрутах.
        Только для административных нужд (мониторинг, очистка).
        """
        self._load()
        with self._lock:
            merged: dict[str, list] = {}
            for uid_sessions in self._data.values():
                merged.update(uid_sessions)
            return merged


conversation_memory = ConversationMemory()
