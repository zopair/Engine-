from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from pathlib import Path
from typing import Iterable

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
    """Deterministic, multilingual-ish CPU feature embeddings with no model downloads."""

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 32:
            raise ValueError("embedding dimension must be at least 32")
        self.dimension = dimension

    def encode(self, text: str) -> tuple[float, ...]:
        if not isinstance(text, str):
            raise TypeError("embedding input must be text")
        vector = [0.0] * self.dimension
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
            digest = hashlib.blake2b(
                feature.encode("utf-8"), digest_size=8, person=b"ENGINEv1"
            ).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return tuple(vector)


class OnnxEmbeddingModel:
    """Optional local ONNX encoder; model and tokenizer must already exist on disk."""

    def __init__(self, model_path: str, tokenizer_path: str, threads: int = 2) -> None:
        if not Path(model_path).is_file() or not Path(tokenizer_path).is_file():
            raise FileNotFoundError("local ONNX model and tokenizer files are required")
        import onnxruntime as ort
        from tokenizers import Tokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(threads, 4))
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            model_path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(tokenizer_path)
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(length=128)
        self.input_names = {item.name for item in self.session.get_inputs()}
        self.dimension = 384

    def encode(self, text: str) -> tuple[float, ...]:
        import numpy as np

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
        vector = output[0]
        norm = float(np.linalg.norm(vector))
        if norm:
            vector = vector / norm
        return tuple(float(value) for value in vector)


class VectorIndex:
    """Bounded exact cosine/IP index implemented with Python floats and no native deps."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self._vectors: list[tuple[float, ...]] = []

    def reset(self, vectors: Iterable[Iterable[float]]) -> None:
        matrix = [tuple(float(value) for value in row) for row in vectors]
        if any(len(row) != self.dimension for row in matrix):
            raise ValueError("vector dimension mismatch")
        self._vectors = matrix

    def add(self, vectors: Iterable[Iterable[float]]) -> None:
        for row in vectors:
            vector = tuple(float(value) for value in row)
            if len(vector) != self.dimension:
                raise ValueError("vector dimension mismatch")
            self._vectors.append(vector)

    def search(self, query: Iterable[float], limit: int) -> tuple[list[float], list[int]]:
        vector = tuple(float(value) for value in query)
        if len(vector) != self.dimension:
            raise ValueError("query dimension mismatch")
        if limit <= 0 or not self._vectors:
            return [], []
        scored = (
            (sum(left * right for left, right in zip(candidate, vector)), index)
            for index, candidate in enumerate(self._vectors)
        )
        top = sorted(scored, key=lambda item: (-item[0], item[1]))[:limit]
        return [score for score, _ in top], [index for _, index in top]
