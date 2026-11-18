from __future__ import annotations

import sqlite3
from pathlib import Path

from huey.contrib.sql_huey import SqliteHuey

from core.config import settings


_queue_path = Path(settings.huey_database_path)
_system_path = Path(settings.database_path)
if _queue_path.resolve() == _system_path.resolve():
    raise ValueError("HUEY_DATABASE_PATH must be different from DATABASE_PATH")
_queue_path.parent.mkdir(parents=True, exist_ok=True)

# Persist WAL mode on the independent Huey database before Huey opens it.
with sqlite3.connect(str(_queue_path), timeout=5.0) as _connection:
    _connection.execute("PRAGMA journal_mode=WAL;")
    _connection.execute("PRAGMA synchronous=NORMAL;")
    _connection.execute("PRAGMA busy_timeout=5000;")

huey = SqliteHuey(
    "ai_engine",
    filename=str(_queue_path),
    timeout=5.0,
    journal_mode="wal",
    fsync=False,
)


@huey.task(retries=2, retry_delay=2)
def persist_conversation(user_id: str, role: str, content: str) -> None:
    from memory.database import database

    with database.connect() as connection:
        connection.execute(
            "INSERT INTO conversations(user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )


@huey.task(retries=2, retry_delay=5)
def store_user_memory(user_id: str, messages: list[dict[str, str]]) -> None:
    from memory.user_memory import user_memory

    for message in messages:
        text = message.get("content", "").strip()
        if text and message.get("role") in {"user", "assistant"}:
            user_memory.add_memory(user_id, text)


@huey.task(retries=2, retry_delay=5)
def run_deep_research(query: str, user_id: str = "") -> dict:
    import asyncio

    from tools.web_research import web_research

    return asyncio.run(web_research.search(query))
