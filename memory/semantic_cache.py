from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import faiss
    from sentence_transformers import SentenceTransformer
except ImportError:
    faiss = None
    SentenceTransformer = None

from core.config import settings


class SemanticCache:
    def __init__(self) -> None:
        self.enabled = settings.semantic_cache_enabled and faiss is not None
        self.dimension = 384
        self.index = faiss.IndexFlatIP(self.dimension) if faiss is not None else None
        self.questions: list[str] = []
        self.answers: list[str] = []
        self.model = None

        if self.enabled:
            try:
                self.model = SentenceTransformer(settings.embedding_model)
            except Exception:
                self.enabled = False

    def _embed(self, text: str):
        if not self.enabled or self.model is None:
            return None
        embedding = self.model.encode([text], normalize_embeddings=True)
        return embedding

    def lookup(self, question: str) -> str | None:
        vector = self._embed(question)
        if vector is None or self.index is None or not self.answers:
            return None

        scores, indices = self.index.search(vector, 1)
        if len(indices[0]) == 0:
            return None

        score = float(scores[0][0])
        index = int(indices[0][0])
        if score >= settings.semantic_similarity_threshold and 0 <= index < len(self.answers):
            return self.answers[index]
        return None

    def put(self, question: str, answer: str) -> None:
        vector = self._embed(question)
        if vector is None or self.index is None:
            return
        self.index.add(vector)
        self.questions.append(question)
        self.answers.append(answer)


semantic_cache = SemanticCache()
