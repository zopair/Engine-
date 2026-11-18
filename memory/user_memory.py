from __future__ import annotations

import asyncio

from memory.database import Database, database


class UserMemory:
    """Local-only user facts and conversation persistence; no remote memory provider."""

    def __init__(self, store: Database | None = None) -> None:
        self.database = store or globals()["database"]
        self.database.initialize()

    def facts(self, user_id: str, limit: int = 20) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT fact FROM user_facts WHERE user_id=?
                   ORDER BY updated_at DESC LIMIT ?""",
                (user_id, max(1, min(int(limit), 100))),
            ).fetchall()
        return [row["fact"] for row in rows]

    def add_fact(self, user_id: str, fact: str, source: str = "conversation") -> None:
        fact = fact.strip()
        if not user_id.strip() or not fact:
            return
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO user_facts(user_id, fact, source) VALUES (?, ?, ?)
                   ON CONFLICT(user_id, fact) DO UPDATE SET
                   source=excluded.source, updated_at=strftime('%s','now')""",
                (user_id, fact[:1000], source[:100]),
            )

    def add_memory(self, user_id: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.add_fact(user_id, text[:500], source="conversation")
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO conversations(user_id, role, content) VALUES (?, 'user', ?)",
                (user_id, text),
            )

    async def enqueue_memory(self, user_id: str, messages: list[dict[str, str]]) -> str:
        def persist() -> int:
            count = 0
            for message in messages:
                role, content = message.get("role", ""), message.get("content", "").strip()
                if role in {"user", "assistant"} and content:
                    with self.database.connect() as connection:
                        connection.execute(
                            "INSERT INTO conversations(user_id, role, content) VALUES (?, ?, ?)",
                            (user_id, role, content),
                        )
                    if role == "user":
                        self.add_fact(user_id, content[:500])
                    count += 1
            return count
        return str(await asyncio.to_thread(persist))


user_memory = UserMemory()
