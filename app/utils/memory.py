import logging

logger = logging.getLogger("Memory")

import json
import os

class ConversationMemory:
    """Хранилище контекста диалога с персистентностью в JSON."""
    
    def __init__(self):
        self._history = {}
        self.file_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'sessions.json')
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
            except:
                pass

    def _save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")

    def add_message(self, session_id: str, role: str, text: str, **kwargs):
        if not session_id:
            return
        if session_id not in self._history:
            self._history[session_id] = []
        msg_data = {"role": role, "text": text}
        import time
        msg_data["timestamp"] = kwargs.pop("timestamp", time.time())
        msg_data.update(kwargs)
        self._history[session_id].append(msg_data)
        self._save()

    def get_context_string(self, session_id: str) -> str:
        if not session_id or session_id not in self._history:
            return ""
        
        lines = []
        # Возвращаем только последние 6 сообщений для LLM
        recent = self._history[session_id][-6:]
        for msg in recent:
            role = "Пользователь" if msg["role"] == "user" else "Система"
            text = msg['text'][:300] + ("..." if len(msg['text']) > 300 else "")
            lines.append(f"{role}: {text}")
            
        return "История диалога:\n" + "\n".join(lines) + "\n"
        
    def get_all_sessions(self) -> dict:
        self._load()
        return self._history

conversation_memory = ConversationMemory()
