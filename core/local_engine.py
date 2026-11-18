"""Lazy CPU-only llama.cpp adapter. No model is downloaded during import or boot."""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from typing import Any, Callable

from core.config import EngineConfig, config


class LocalEngineError(RuntimeError):
    """Raised when local inference cannot be initialized or executed."""


class LocalEngine:
    def __init__(
        self,
        settings: EngineConfig = config,
        llama_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self._factory = llama_factory
        self._model: Any = None
        self._lock = threading.Lock()

    @staticmethod
    def runtime_installed() -> bool:
        return importlib.util.find_spec("llama_cpp") is not None

    def is_ready(self) -> bool:
        return bool(self.settings.model_path and Path(self.settings.model_path).is_file())

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            model_path = Path(self.settings.model_path).expanduser()
            if not model_path.is_file():
                raise LocalEngineError(
                    "GGUF model not found. Set ENGINE_MODEL_PATH to a cached model file."
                )
            factory = self._factory
            if factory is None:
                try:
                    from llama_cpp import Llama
                except ImportError as exc:
                    raise LocalEngineError(
                        "llama-cpp-python is not installed in this runner; "
                        "the runtime must pass the license and dependency gate before installation."
                    ) from exc
                factory = Llama
            self._model = factory(
                model_path=str(model_path),
                n_ctx=self.settings.model_context,
                n_threads=self.settings.model_threads,
                n_batch=self.settings.model_batch,
                n_gpu_layers=0,
                verbose=False,
                use_mmap=True,
                use_mlock=False,
            )
            return self._model

    def complete(self, prompt: str, max_tokens: int | None = None) -> str:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        result = self._load().create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or self.settings.max_tokens,
            temperature=self.settings.temperature,
        )
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalEngineError("llama.cpp returned an invalid completion payload") from exc
        if not isinstance(content, str):
            raise LocalEngineError("llama.cpp returned non-text completion content")
        return content.strip()
