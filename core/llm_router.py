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
    def __init__(self) -> None:
        self.router: Any = None
        self.default_model: str | None = None
        if Router is None:
            return

        model_list: list[dict[str, Any]] = []
        fallback_chain: list[str] = []

        for model in filter(None, (part.strip() for part in settings.groq_models.split(","))):
            if settings.groq_api_key:
                alias = "groq-primary"
                model_list.append({"model_name": alias, "litellm_params": {
                    "model": f"groq/{model}", "api_key": settings.groq_api_key,
                    "timeout": settings.max_request_timeout,
                }})
                if alias not in fallback_chain:
                    fallback_chain.append(alias)

        if settings.gemini_api_key:
            alias = "gemini-flash"
            model_list.append({"model_name": alias, "litellm_params": {
                "model": f"gemini/{settings.gemini_model}", "api_key": settings.gemini_api_key,
                "timeout": settings.max_request_timeout,
            }})
            fallback_chain.append(alias)

        if settings.openrouter_api_key:
            for model in filter(None, (part.strip() for part in settings.openrouter_free_models.split(","))):
                alias = "openrouter-free"
                model_list.append({"model_name": alias, "litellm_params": {
                    "model": f"openrouter/{model}", "api_key": settings.openrouter_api_key,
                    "timeout": settings.max_request_timeout,
                }})
                if alias not in fallback_chain:
                    fallback_chain.append(alias)

        if model_list:
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

    async def acompletion(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        if self.router is None or self.default_model is None:
            raise RuntimeError("No LLM provider configured; add a Groq, Gemini, or OpenRouter API key")
        requested_model = kwargs.pop("model", None)
        model = requested_model if requested_model and requested_model != "auto" else self.default_model
        try:
            return await self.router.acompletion(model=model, messages=messages, **kwargs)
        except Exception:
            logger.exception("All configured LLM providers failed")
            raise


llm_router = LLMRouter()
