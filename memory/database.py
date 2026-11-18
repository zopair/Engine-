from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config import settings


class Database:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or settings.database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        connection.execute("PRAGMA foreign_keys=ON;")
        connection.execute("PRAGMA busy_timeout=30000;")
        connection.execute("PRAGMA temp_store=MEMORY;")
        connection.execute("PRAGMA cache_size=-8192;")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                );

                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NOT NULL,
                    source TEXT,
                    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
                    UNIQUE(user_id, fact)
                );

                CREATE TABLE IF NOT EXISTS semantic_cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    embedding BLOB,
                    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_user_created
                    ON conversations(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_user_facts_user
                    ON user_facts(user_id);
            """)


database = Database()
