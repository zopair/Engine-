from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.config import settings
from memory.database import database

logger = logging.getLogger(__name__)

try:
    from mem0 import Memory
except ImportError:
    Memory = None


class UserMemory:
    def __init__(self) -> None:
        self.memory: Any = None
        self._memory_lock = asyncio.Lock()

    def _create_mem0(self) -> Any:
        if not settings.mem0_enabled or Memory is None:
            return None
        try:
            if settings.groq_api_key:
                model = settings.groq_models.split(",")[0].strip()
                return Memory.from_config({
                    "version": "v1.1",
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": model,
                            "api_key": settings.groq_api_key,
                            "openai_base_url": "https://api.groq.com/openai/v1",
                            "temperature": 0.1,
                            "max_tokens": 800,
                        },
                    },
                    "embedder": {
                        "provider": "huggingface",
                        "config": {"model": "sentence-transformers/all-MiniLM-L6-v2"},
                    },
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {"collection_name": "engine_user_memory", "path": "./data/mem0"},
                    },
                })
            return None
        except Exception as exc:
            logger.warning("mem0 is unavailable; using SQLite user facts: %s", exc)
            return None

    def _mem0(self) -> Any:
        if self.memory is None:
            self.memory = self._create_mem0()
        return self.memory

    def facts(self, user_id: str) -> list[str]:
        try:
            memory = self._mem0()
            if memory is not None:
                result = memory.search("user preferences and known facts", user_id=user_id, limit=10)
                items = result.get("results", []) if isinstance(result, dict) else []
                facts = [str(item.get("memory", "")).strip() for item in items]
                return [fact for fact in facts if fact]
        except Exception as exc:
            logger.warning("mem0 search failed: %s", exc)
        with database.connect() as connection:
            rows = connection.execute(
                "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY updated_at DESC LIMIT 20",
                (user_id,),
            ).fetchall()
        return [row["fact"] for row in rows]

    def add_memory(self, user_id: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        try:
            memory = self._mem0()
            if memory is not None:
                memory.add(text, user_id=user_id)
        except Exception as exc:
            logger.warning("mem0 add failed: %s", exc)
        self.add_fact(user_id, text[:500], source="conversation")

    def add_fact(self, user_id: str, fact: str, source: str = "conversation") -> None:
        fact = fact.strip()
        if not fact:
            return
        with database.connect() as connection:
            connection.execute(
                """INSERT INTO user_facts(user_id, fact, source) VALUES (?, ?, ?)
                   ON CONFLICT(user_id, fact) DO UPDATE SET
                   updated_at=strftime('%s', 'now'), source=excluded.source""",
                (user_id, fact, source),
            )

    async def enqueue_memory(self, user_id: str, messages: list[dict[str, str]]) -> str:
        from memory.task_queue import store_user_memory

        try:
            result = store_user_memory(user_id, messages)
            return str(getattr(result, "id", "queued"))
        except Exception as exc:
            logger.warning("Could not queue user memory update: %s", exc)
            return "not-queued"


user_memory = UserMemory()
