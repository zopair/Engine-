from __future__ import annotations

import logging
from typing import Any

from core.llm_router import llm_router
from core.local_llm import LocalLlamaBackend

logger = logging.getLogger(__name__)


class InferenceEngine:
    """Prefer a configured local GGUF model, then fall back to LiteLLM providers."""

    def __init__(
        self,
        local_backend: Any | None = None,
        remote_backend: Any | None = None,
    ) -> None:
        self.local_backend = local_backend or LocalLlamaBackend()
        self.remote_backend = remote_backend or llm_router

    async def acompletion(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> Any:
        if self.local_backend.is_available():
            try:
                return await self.local_backend.acompletion(messages, **kwargs)
            except Exception:
                if not self.remote_backend.is_available():
                    raise
                logger.exception("Local GGUF inference failed; trying configured remote fallback")

        if self.remote_backend.is_available():
            return await self.remote_backend.acompletion(messages, **kwargs)

        raise RuntimeError(
            "No inference backend is ready. Configure LOCAL_MODEL_PATH with an existing "
            "GGUF file, or set a supported provider API key. The API can start without either."
        )


inference_engine = InferenceEngine()
