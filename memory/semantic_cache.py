from __future__ import annotations

import json
import logging
import os
import struct
from dataclasses import dataclass
from typing import Any

from core.config import settings
from memory.database import Database, database
from memory.embeddings import CpuHashEmbeddingModel, OnnxEmbeddingModel, VectorIndex

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CacheHit:
    question: str
    answer: str
    score: float
    metadata: dict[str, Any]


class SemanticCache:
    """Persistent namespaced semantic cache using a local CPU embedding encoder."""

    def __init__(
        self,
        database: Database | None = None,
        namespace: str = "default",
        embedder: Any | None = None,
        similarity_threshold: float | None = None,
        max_entries: int = 5000,
    ) -> None:
        if not namespace.strip():
            raise ValueError("namespace must not be empty")
        self.database = database or globals()["database"]
        self.database.initialize()
        self.namespace = namespace
        self.embedder = embedder or self._build_embedder()
        self.dimension = int(self.embedder.dimension)
        self.threshold = settings.semantic_similarity_threshold if similarity_threshold is None else float(similarity_threshold)
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("similarity threshold must be between 0 and 1")
        self.max_entries = max(1, int(max_entries))
        self.index = VectorIndex(self.dimension)
        self._items: list[CacheHit] = []
        self._load()

    @staticmethod
    def _build_embedder():
        model_path = os.getenv("ENGINE_EMBEDDING_MODEL_PATH", "").strip()
        tokenizer_path = os.getenv("ENGINE_EMBEDDING_TOKENIZER_PATH", "").strip()
        if model_path and tokenizer_path:
            try:
                return OnnxEmbeddingModel(model_path, tokenizer_path)
            except (ImportError, OSError, ValueError) as exc:
                logger.warning("Local ONNX encoder unavailable; using CPU feature embeddings: %s", exc)
        return CpuHashEmbeddingModel()

    def _load(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT question, answer, embedding, embedding_dim, metadata_json
                   FROM semantic_cache_entries WHERE namespace=?
                   ORDER BY updated_at DESC LIMIT ?""",
                (self.namespace, self.max_entries),
            ).fetchall()
        items, vectors = [], []
        for row in rows:
            if int(row["embedding_dim"]) != self.dimension:
                continue
            try:
                vector = struct.unpack(f"{self.dimension}f", row["embedding"])
                metadata = json.loads(row["metadata_json"] or "{}")
            except (ValueError, TypeError, struct.error, json.JSONDecodeError):
                continue
            vectors.append(vector)
            items.append(CacheHit(row["question"], row["answer"], 0.0, metadata))
        self._items = items
        self.index.reset(vectors)

    def put(self, question: str, answer: str, metadata: dict[str, Any] | None = None) -> None:
        question, answer = question.strip(), answer.strip()
        if not question or not answer:
            raise ValueError("question and answer must not be empty")
        vector = self.embedder.encode(question)
        blob = struct.pack(f"{self.dimension}f", *vector)
        encoded_metadata = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO semantic_cache_entries
                   (namespace, question, answer, embedding, embedding_dim, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(namespace, question) DO UPDATE SET
                   answer=excluded.answer, embedding=excluded.embedding,
                   embedding_dim=excluded.embedding_dim, metadata_json=excluded.metadata_json,
                   updated_at=strftime('%s','now')""",
                (self.namespace, question, answer, blob, self.dimension, encoded_metadata),
            )
            connection.execute(
                """DELETE FROM semantic_cache_entries WHERE namespace=? AND id NOT IN
                   (SELECT id FROM semantic_cache_entries WHERE namespace=?
                    ORDER BY updated_at DESC, id DESC LIMIT ?)""",
                (self.namespace, self.namespace, self.max_entries),
            )
        self._load()

    def lookup_hit(self, question: str, threshold: float | None = None) -> CacheHit | None:
        if not question.strip() or not self._items:
            return None
        scores, indices = self.index.search(self.embedder.encode(question), 1)
        if not indices:
            return None
        position, score = indices[0], scores[0]
        minimum = self.threshold if threshold is None else float(threshold)
        if score < minimum:
            return None
        item = self._items[position]
        return CacheHit(item.question, item.answer, score, item.metadata)

    def lookup(self, question: str, threshold: float | None = None) -> str | None:
        hit = self.lookup_hit(question, threshold)
        return hit.answer if hit else None

    def clear(self) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM semantic_cache_entries WHERE namespace=?", (self.namespace,))
        self._load()
