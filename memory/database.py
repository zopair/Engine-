from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config import settings


class Database:
    """Small WAL-backed store for memory, knowledge, and resumable workflows."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or settings.database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=15.0, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA cache_size=-8192")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            legacy_cache = False
            if "semantic_cache_entries" in tables:
                columns = {
                    row["name"] for row in connection.execute(
                        "PRAGMA table_info(semantic_cache_entries)"
                    )
                }
                if "namespace" not in columns:
                    connection.execute(
                        "ALTER TABLE semantic_cache_entries RENAME TO semantic_cache_entries_legacy"
                    )
                    legacy_cache = True

            connection.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('system','user','assistant','tool')),
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                );
                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    source TEXT,
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    UNIQUE(user_id, fact)
                );
                CREATE TABLE IF NOT EXISTS semantic_cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL DEFAULT 'default',
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    UNIQUE(namespace, question)
                );
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL DEFAULT 'default',
                    source TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    embedding BLOB NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                    UNIQUE(namespace, source)
                );
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','running','failed','completed')),
                    input_json TEXT NOT NULL,
                    outputs_json TEXT NOT NULL DEFAULT '{}',
                    lease_owner TEXT,
                    lease_until REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
                    step_name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','running','failed','completed')),
                    output_json TEXT,
                    error TEXT,
                    started_at REAL,
                    completed_at REAL,
                    UNIQUE(run_id, step_name)
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_user_created
                    ON conversations(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_user_facts_user
                    ON user_facts(user_id);
                CREATE INDEX IF NOT EXISTS idx_semantic_namespace
                    ON semantic_cache_entries(namespace, updated_at);
                CREATE INDEX IF NOT EXISTS idx_knowledge_namespace
                    ON knowledge_items(namespace, updated_at);
                CREATE INDEX IF NOT EXISTS idx_workflow_status
                    ON workflow_runs(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_workflow_steps_run
                    ON workflow_steps(run_id, position);
            """)
            if legacy_cache:
                connection.execute("""
                    INSERT OR IGNORE INTO semantic_cache_entries
                    (namespace, question, answer, embedding, embedding_dim, metadata_json, created_at, updated_at)
                    SELECT 'default', question, answer, embedding, 384, '{}', created_at, created_at
                    FROM semantic_cache_entries_legacy
                """)
                connection.execute("DROP TABLE semantic_cache_entries_legacy")

    def backup_to(self, destination: str | Path) -> None:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.path)) as source, sqlite3.connect(str(target)) as backup:
            source.backup(backup)


database = Database()
