from pathlib import Path

try:
    from huey import crontab
except ImportError:
    crontab = None

from memory.task_queue import huey
from memory.database import database
from memory.user_memory import user_memory


@huey.task()
def update_user_memory(user_id: str, messages: list[dict[str, str]]) -> None:
    for message in messages:
        if message.get("role") != "assistant":
            continue
        content = message.get("content", "").strip()
        if content:
            user_memory.add_fact(user_id, content[:500], source="conversation")


@huey.task()
def persist_conversation(user_id: str, role: str, content: str) -> None:
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO conversations(user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
