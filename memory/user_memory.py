from __future__ import annotations

from typing import Iterable

from core.config import settings

try:
    from mem0 import Memory
except ImportError:
    Memory = None

from memory.database import database


class UserMemory:
    def __init__(self) -> None:
        self.memory = None
        if Memory is not None:
            try:
                self.memory = Memory()
            except Exception:
                self.memory = None

    def facts(self, user_id: str) -> list[str]:
        with database.connect() as connection:
            rows = connection.execute(
                "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY updated_at DESC LIMIT 20",
                (user_id,),
            ).fetchall()
        return [row["fact"] for row in rows]

    def add_fact(self, user_id: str, fact: str, source: str = "conversation") -> None:
        fact = fact.strip()
        if not fact:
            return
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO user_facts(user_id, fact, source)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, fact) DO UPDATE SET
                    updated_at = strftime('%s', 'now'), source = excluded.source
                """,
                (user_id, fact, source),
            )


user_memory = UserMemory()
