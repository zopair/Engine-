from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from core.config import settings

try:
    from litellm import Router
except ImportError:
    Router = None


class LLMRouter:
    def __init__(self) -> None:
        self.request_counts: defaultdict[str, int] = defaultdict(int)
        self.failures: defaultdict[str, int] = defaultdict(int)

        model_list: list[dict[str, Any]] = []

        if settings.groq_api_key:
            for model in settings.groq_models.split(","):
                model_list.append({
                    "model_name": model.strip(),
                    "litellm_params": {
                        "model": f"groq/{model.strip()}",
                        "api_key": settings.groq_api_key,
                    },
                })

        if settings.gemini_api_key:
            model_list.append({
                "model_name": settings.gemini_model,
                "litellm_params": {
                    "model": f"gemini/{settings.gemini_model}",
                    "api_key": settings.gemini_api_key,
                },
            })

        if settings.openrouter_api_key:
            model_list.append({
                "model_name": "openrouter/free",
                "litellm_params": {
                    "model": "openrouter/free",
                    "api_key": settings.openrouter_api_key,
                },
            })

        if Router is not None and model_list:
            self.router = Router(
                model_list=model_list,
                routing_strategy="simple-shuffle",
                num_retries=2,
                timeout=settings.max_request_timeout,
            )
        else:
            self.router = None

    async def acompletion(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        if self.router is None:
            raise RuntimeError("No usable LLM provider is configured")

        model = kwargs.pop("model", None)
        try:
            return await self.router.acompletion(messages=messages, model=model, **kwargs)
        except Exception:
            raise


llm_router = LLMRouter()
