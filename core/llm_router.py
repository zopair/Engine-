from __future__ import annotations

import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

try:
    from litellm import Router
except ImportError:
    Router = None


class LLMRouter:
    """Optional LiteLLM provider router; no credentials are required to import it."""

    def __init__(self) -> None:
        self.router: Any = None
        self.default_model: str | None = None
        if Router is None:
            return

        model_list: list[dict[str, Any]] = []
        fallback_chain: list[str] = []

        if settings.groq_api_key:
            for index, model in enumerate(
                filter(None, (part.strip() for part in settings.groq_models.split(",")))
            ):
                alias = f"groq-{index}"
                model_list.append({
                    "model_name": alias,
                    "litellm_params": {
                        "model": f"groq/{model}",
                        "api_key": settings.groq_api_key,
                        "timeout": settings.max_request_timeout,
                    },
                })
                fallback_chain.append(alias)

        if settings.gemini_api_key:
            alias = "gemini-primary"
            model_list.append({
                "model_name": alias,
                "litellm_params": {
                    "model": f"gemini/{settings.gemini_model}",
                    "api_key": settings.gemini_api_key,
                    "timeout": settings.max_request_timeout,
                },
            })
            fallback_chain.append(alias)

        if settings.openrouter_api_key:
            for index, model in enumerate(
                filter(None, (part.strip() for part in settings.openrouter_free_models.split(",")))
            ):
                alias = f"openrouter-{index}"
                model_list.append({
                    "model_name": alias,
                    "litellm_params": {
                        "model": f"openrouter/{model}",
                        "api_key": settings.openrouter_api_key,
                        "timeout": settings.max_request_timeout,
                    },
                })
                fallback_chain.append(alias)

        if not model_list:
            return

        fallbacks = [
            {fallback_chain[index]: fallback_chain[index + 1:]}
            for index in range(len(fallback_chain) - 1)
        ]
        try:
            self.router = Router(
                model_list=model_list,
                fallbacks=fallbacks,
                num_retries=1,
                timeout=settings.max_request_timeout,
                routing_strategy="simple-shuffle",
            )
            self.default_model = fallback_chain[0]
        except Exception as exc:
            logger.exception("LiteLLM Router setup failed: %s", exc)

    def is_available(self) -> bool:
        return self.router is not None and self.default_model is not None

    async def acompletion(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        if not self.is_available():
            raise RuntimeError(
                "No remote LLM provider configured; set a supported provider API key."
            )
        requested_model = kwargs.pop("model", None)
        model = requested_model if requested_model and requested_model != "auto" else self.default_model
        try:
            return await self.router.acompletion(model=model, messages=messages, **kwargs)
        except Exception:
            logger.exception("All configured LiteLLM providers failed")
            raise


llm_router = LLMRouter()
