from __future__ import annotations

import asyncio
import logging

from core.config import settings

logger = logging.getLogger(__name__)


def _dspy_optimize(prompt: str) -> str:
    import dspy

    class RequestStructure(dspy.Signature):
        """Rewrite a user request as concise, explicit instructions for a small language model."""

        request: str = dspy.InputField()
        structured_instructions: str = dspy.OutputField()

    if settings.dspy_model:
        import litellm
        dspy.configure(lm=dspy.LM(settings.dspy_model, api_key=None))
    result = dspy.Predict(RequestStructure)(request=prompt)
    optimized = getattr(result, "structured_instructions", "")
    return optimized.strip() if optimized and optimized.strip() else prompt


async def optimize_instructions(prompt: str) -> str:
    """Use DSPy when a model is configured; otherwise return a deterministic structured prompt."""
    prompt = prompt.strip()
    if not prompt:
        return prompt
    if settings.dspy_model:
        try:
            return await asyncio.wait_for(asyncio.to_thread(_dspy_optimize, prompt), timeout=settings.max_request_timeout)
        except Exception as exc:
            logger.warning("DSPy optimization failed; using local structure: %s", exc)
    return (
        "Understand the request and its constraints. Distinguish known facts from assumptions. "
        "Answer directly and accurately; if information is missing, state that clearly.\n\n"
        f"User request:\n{prompt}"
    )
