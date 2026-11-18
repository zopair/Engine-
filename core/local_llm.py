from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Callable

from core.config import settings


class LocalLlamaBackend:
    """Lazy-loaded llama.cpp backend with GPU offload explicitly disabled."""

    def __init__(
        self,
        model_path: str | None = None,
        llama_factory: Callable[..., Any] | None = None,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        n_batch: int | None = None,
    ) -> None:
        self.model_path = Path(model_path or settings.local_model_path).expanduser()
        self.llama_factory = llama_factory
        self.n_ctx = n_ctx or settings.local_model_n_ctx
        self.n_threads = n_threads or settings.local_model_n_threads
        self.n_batch = n_batch or settings.local_model_n_batch
        self._model: Any = None
        self._load_lock = threading.Lock()

    def _factory(self) -> Callable[..., Any] | None:
        if self.llama_factory is not None:
            return self.llama_factory
        try:
            from llama_cpp import Llama
        except ImportError:
            return None
        return Llama

    def is_available(self) -> bool:
        return self.model_path.is_file() and self._factory() is not None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            if not self.model_path.is_file():
                raise FileNotFoundError(
                    f"GGUF model file not found: {self.model_path}. "
                    "Set LOCAL_MODEL_PATH to an existing local model."
                )
            factory = self._factory()
            if factory is None:
                raise RuntimeError(
                    "llama-cpp-python is not installed. Install the CPU runtime "
                    "from requirements.txt before using local inference."
                )
            self._model = factory(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=max(1, self.n_threads),
                n_batch=max(1, self.n_batch),
                n_gpu_layers=0,
                verbose=False,
            )
            return self._model

    def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        return self._load().create_chat_completion(messages=messages, **kwargs)

    async def acompletion(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        return await asyncio.to_thread(self.complete, messages, **kwargs)
