from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None


_STOP = {
    "a", "an", "and", "are", "do", "does", "for", "how", "i", "in", "is",
    "it", "me", "my", "of", "on", "or", "the", "to", "what", "with",
    "ما", "من", "في", "على", "كيف", "هل", "انا", "أنا", "هو", "هي",
}
_SYNONYMS = {
    "purchase": "buy", "purchased": "buy", "buying": "buy", "order": "buy",
    "recover": "reset", "recovery": "reset", "restore": "reset",
    "passcode": "password", "credential": "password",
    "استرجاع": "استعادة", "استرجع": "استعادة", "استعادة": "استعادة",
    "شراء": "شراء", "اشترى": "شراء", "اشتري": "شراء",
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))


class CpuHashEmbeddingModel:
    """Deterministic CPU feature-embedding model; no network or model download."""

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 32:
            raise ValueError("embedding dimension must be at least 32")
        self.dimension = dimension

    def encode(self, text: str) -> np.ndarray:
        if not isinstance(text, str):
            raise TypeError("embedding input must be text")
        vector = np.zeros(self.dimension, dtype=np.float32)
        tokens = [_SYNONYMS.get(token, token) for token in re.findall(r"\w+", _normalize(text))]
        tokens = [token for token in tokens if token and token not in _STOP]
        features: list[tuple[str, float]] = [(token, 2.0) for token in tokens]
        features.extend((f"pair:{a}_{b}", 1.1) for a, b in zip(tokens, tokens[1:]))
        for token in tokens:
            if len(token) >= 3:
                padded = f"^{token}$"
                for width in (3, 4):
                    features.extend(
                        (f"char:{padded[i:i + width]}", 0.25)
                        for i in range(max(0, len(padded) - width + 1))
                    )
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8, person=b"ENGINEv1").digest()
            index = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * weight
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return np.ascontiguousarray(vector.reshape(1, -1), dtype=np.float32)


class OnnxEmbeddingModel:
    """Optional local ONNX encoder. Model and tokenizer files must already exist locally."""

    def __init__(self, model_path: str, tokenizer_path: str, threads: int = 2) -> None:
        model, tokenizer = Path(model_path), Path(tokenizer_path)
        if not model.is_file() or not tokenizer.is_file():
            raise FileNotFoundError("local ONNX model and tokenizer files are required")
        import onnxruntime as ort
        from tokenizers import Tokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(threads, 4))
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(model), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(length=128)
        self.input_names = {item.name for item in self.session.get_inputs()}
        self.dimension = 384

    def encode(self, text: str) -> np.ndarray:
        encoded = self.tokenizer.encode(text)
        attention = np.asarray([encoded.attention_mask], dtype=np.int64)
        available = {
            "input_ids": np.asarray([encoded.ids], dtype=np.int64),
            "attention_mask": attention,
            "token_type_ids": np.asarray([encoded.type_ids], dtype=np.int64),
        }
        feed = {key: value for key, value in available.items() if key in self.input_names}
        output = np.asarray(self.session.run(None, feed)[0], dtype=np.float32)
        if output.ndim == 3:
            mask = attention.astype(np.float32)[..., None]
            output = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
        if output.ndim != 2:
            raise ValueError("ONNX model must return a 2D or 3D embedding tensor")
        self.dimension = int(output.shape[1])
        output /= np.maximum(np.linalg.norm(output, axis=1, keepdims=True), 1e-12)
        return np.ascontiguousarray(output, dtype=np.float32)


class VectorIndex:
    """FAISS inner-product index with a deterministic NumPy fallback for tests/minimal installs."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self._vectors = np.empty((0, dimension), dtype=np.float32)
        self._index = faiss.IndexFlatIP(dimension) if faiss is not None else None

    def reset(self, vectors: np.ndarray) -> None:
        matrix = np.ascontiguousarray(vectors, dtype=np.float32).reshape(-1, self.dimension)
        self._vectors = matrix
        if self._index is not None:
            self._index = faiss.IndexFlatIP(self.dimension)
            if len(matrix):
                self._index.add(matrix)

    def add(self, vectors: np.ndarray) -> None:
        matrix = np.ascontiguousarray(vectors, dtype=np.float32).reshape(-1, self.dimension)
        self._vectors = np.vstack((self._vectors, matrix))
        if self._index is not None:
            self._index.add(matrix)

    def search(self, query: np.ndarray, limit: int) -> tuple[np.ndarray, np.ndarray]:
        if not len(self._vectors) or limit <= 0:
            return np.empty((1, 0), np.float32), np.empty((1, 0), np.int64)
        count = min(limit, len(self._vectors))
        query = np.ascontiguousarray(query, dtype=np.float32).reshape(1, self.dimension)
        if self._index is not None:
            return self._index.search(query, count)
        scores = self._vectors @ query[0]
        indices = np.argsort(-scores)[:count]
        return scores[indices].reshape(1, -1), indices.astype(np.int64).reshape(1, -1)
