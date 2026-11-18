from __future__ import annotations

import asyncio
import logging
import sqlite3
import struct
from typing import Any

import numpy as np

from core.config import settings
from memory.database import database

logger = logging.getLogger(__name__)

try:
    import faiss
except ImportError:
    faiss = None

try:
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer
except ImportError:
    ort = None
    hf_hub_download = None
    Tokenizer = None


class SemanticCache:
    """CPU-only FAISS cache backed by ONNX Runtime and a compact MiniLM model."""

    def __init__(self) -> None:
        self.enabled = bool(settings.semantic_cache_enabled and faiss and ort and Tokenizer)
        self.dimension = 384
        self.index = faiss.IndexFlatIP(self.dimension) if self.enabled else None
        self.questions: list[str] = []
        self.answers: list[str] = []
        self.tokenizer: Any = None
        self.session: Any = None
        self._initialize_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        if not self.enabled or self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            try:
                await asyncio.wait_for(asyncio.to_thread(self._load_model), settings.embedding_download_timeout)
                await asyncio.to_thread(self._load_entries)
                self._initialized = True
            except Exception as exc:
                logger.warning("Semantic cache initialization failed: %s", exc)
                self.enabled = False

    def _load_model(self) -> None:
        model_file = hf_hub_download(
            repo_id=settings.embedding_model,
            filename="onnx/model.onnx",
            token=settings.hf_token or None,
        )
        tokenizer_file = hf_hub_download(
            repo_id=settings.embedding_model,
            filename="tokenizer.json",
            token=settings.hf_token or None,
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            model_file, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(tokenizer_file)
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(length=128)

    def _load_entries(self) -> None:
        with database.connect() as connection:
            rows = connection.execute(
                "SELECT question, answer, embedding FROM semantic_cache_entries ORDER BY id"
            ).fetchall()
        vectors: list[np.ndarray] = []
        for row in rows:
            try:
                vector = np.frombuffer(row["embedding"], dtype=np.float32)
                if vector.size != self.dimension:
                    continue
                vectors.append(vector.copy())
                self.questions.append(row["question"])
                self.answers.append(row["answer"])
            except (TypeError, ValueError):
                logger.warning("Skipping invalid embedding in semantic cache")
        if vectors and self.index is not None:
            self.index.add(np.ascontiguousarray(vectors, dtype=np.float32))

    def _embed_sync(self, text: str) -> np.ndarray:
        if self.session is None or self.tokenizer is None:
            raise RuntimeError("Semantic cache model is not initialized")
        encoded = self.tokenizer.encode(text)
        ids = np.asarray([encoded.ids], dtype=np.int64)
        attention = np.asarray([encoded.attention_mask], dtype=np.int64)
        type_ids = np.asarray([encoded.type_ids], dtype=np.int64)
        input_map = {item.name for item in self.session.get_inputs()}
        feed: dict[str, np.ndarray] = {}
        if "input_ids" in input_map:
            feed["input_ids"] = ids
        if "attention_mask" in input_map:
            feed["attention_mask"] = attention
        if "token_type_ids" in input_map:
            feed["token_type_ids"] = type_ids
        output = self.session.run(None, feed)[0]
        if output.ndim == 3:
            mask = attention.astype(np.float32)[..., None]
            vector = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
        elif output.ndim == 2:
            vector = output
        else:
            raise ValueError("Unexpected ONNX embedding output shape")
        vector = np.asarray(vector, dtype=np.float32)
        vector /= np.maximum(np.linalg.norm(vector, axis=1, keepdims=True), 1e-12)
        return np.ascontiguousarray(vector)

    async def lookup(self, question: str) -> str | None:
        await self.initialize()
        if not self.enabled or self.index is None or not self.answers:
            return None
        try:
            vector = await asyncio.to_thread(self._embed_sync, question)
            scores, indices = self.index.search(vector, 1)
            idx = int(indices[0][0])
            if idx >= 0 and float(scores[0][0]) >= settings.semantic_similarity_threshold:
                return self.answers[idx]
        except Exception as exc:
            logger.warning("Semantic cache lookup failed: %s", exc)
        return None

    async def put(self, question: str, answer: str) -> None:
        await self.initialize()
        if not self.enabled or self.index is None:
            return
        try:
            vector = await asyncio.to_thread(self._embed_sync, question)
            blob = struct.pack(f"{self.dimension}f", *vector[0].tolist())
            with database.connect() as connection:
                connection.execute(
                    """INSERT INTO semantic_cache_entries(question, answer, embedding)
                       VALUES (?, ?, ?) ON CONFLICT(question) DO UPDATE SET
                       answer=excluded.answer, embedding=excluded.embedding""",
                    (question, answer, blob),
                )
            self.index.add(vector)
            self.questions.append(question)
            self.answers.append(answer)
        except Exception as exc:
            logger.warning("Semantic cache insert failed: %s", exc)


semantic_cache = SemanticCache()
