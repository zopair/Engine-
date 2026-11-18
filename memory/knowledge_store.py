from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Any

from memory.database import Database, database
from memory.embeddings import CpuHashEmbeddingModel, VectorIndex


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: int
    namespace: str
    source: str
    title: str
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class KnowledgeResult(KnowledgeDocument):
    score: float


class KnowledgeStore:
    """SQLite-backed repository knowledge with bounded CPU vector retrieval."""

    def __init__(self, database: Database | None = None, namespace: str = "default",
                 embedder: Any | None = None, max_documents: int = 10000) -> None:
        if not namespace.strip():
            raise ValueError("namespace must not be empty")
        self.database = database or globals()["database"]
        self.database.initialize()
        self.namespace = namespace
        self.embedder = embedder or CpuHashEmbeddingModel()
        self.dimension = int(self.embedder.dimension)
        self.max_documents = max(1, int(max_documents))
        self.index = VectorIndex(self.dimension)
        self._documents: list[KnowledgeDocument] = []
        self._load()

    def _load(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, namespace, source, title, content, metadata_json, embedding, embedding_dim
                   FROM knowledge_items WHERE namespace=? ORDER BY updated_at DESC LIMIT ?""",
                (self.namespace, self.max_documents),
            ).fetchall()
        documents, vectors = [], []
        for row in rows:
            if int(row["embedding_dim"]) != self.dimension:
                continue
            try:
                vector = struct.unpack(f"{self.dimension}f", row["embedding"])
                metadata = json.loads(row["metadata_json"] or "{}")
            except (ValueError, TypeError, struct.error, json.JSONDecodeError):
                continue
            documents.append(KnowledgeDocument(
                int(row["id"]), row["namespace"], row["source"],
                row["title"], row["content"], metadata
            ))
            vectors.append(vector)
        self._documents = documents
        self.index.reset(vectors)

    def upsert(self, source: str, content: str, title: str = "",
               metadata: dict[str, Any] | None = None) -> int:
        source, content = source.strip(), content.strip()
        if not source or not content:
            raise ValueError("source and content must not be empty")
        vector = self.embedder.encode(f"{title}\n{content}")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        blob = struct.pack(f"{self.dimension}f", *vector)
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO knowledge_items
                   (namespace, source, title, content, content_hash, metadata_json, embedding, embedding_dim)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(namespace, source) DO UPDATE SET
                   title=excluded.title, content=excluded.content, content_hash=excluded.content_hash,
                   metadata_json=excluded.metadata_json, embedding=excluded.embedding,
                   embedding_dim=excluded.embedding_dim, updated_at=strftime('%s','now')""",
                (self.namespace, source, title, content, digest, metadata_json, blob, self.dimension),
            )
            row = connection.execute(
                "SELECT id FROM knowledge_items WHERE namespace=? AND source=?",
                (self.namespace, source),
            ).fetchone()
            item_id = int(row["id"])
        self._load()
        return item_id

    def get(self, item_id: int) -> KnowledgeDocument | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT id, namespace, source, title, content, metadata_json
                   FROM knowledge_items WHERE id=? AND namespace=?""",
                (item_id, self.namespace),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeDocument(
            int(row["id"]), row["namespace"], row["source"], row["title"],
            row["content"], json.loads(row["metadata_json"] or "{}")
        )

    def search(self, query: str, limit: int = 5, threshold: float = 0.0) -> list[KnowledgeResult]:
        if not query.strip() or not self._documents or limit <= 0:
            return []
        scores, indices = self.index.search(self.embedder.encode(query), limit)
        return [
            KnowledgeResult(
                item.id, item.namespace, item.source, item.title,
                item.content, item.metadata, score
            )
            for score, position in zip(scores, indices)
            if score >= threshold
            for item in [self._documents[position]]
        ]

    def delete(self, item_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM knowledge_items WHERE id=? AND namespace=?",
                (item_id, self.namespace),
            )
        self._load()
        return cursor.rowcount > 0
