from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

try:
    from gradio_client import Client
except ImportError:
    Client = None


class MediaGenerator:
    def __init__(self) -> None:
        self.output_dir = Path(settings.media_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _generate_sync(self, prompt: str) -> Any:
        if Client is None:
            raise RuntimeError("gradio_client is not installed")
        client = Client(
            settings.hf_image_space,
            token=settings.hf_token or None,
            verbose=False,
        )
        return client.predict(prompt=prompt, api_name=settings.hf_image_api_name)

    async def generate(self, prompt: str, timeout: float = 120.0) -> dict[str, str]:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Image prompt cannot be empty")
        try:
            result = await asyncio.wait_for(asyncio.to_thread(self._generate_sync, prompt), timeout=timeout)
            paths = result if isinstance(result, list) else [result]
            artifacts: list[str] = []
            for item in paths:
                path_value = item.get("path") if isinstance(item, dict) else getattr(item, "path", None)
                if path_value:
                    source = Path(str(path_value))
                    if source.is_file():
                        destination = self.output_dir / source.name
                        await asyncio.to_thread(destination.write_bytes, await asyncio.to_thread(source.read_bytes))
                        artifacts.append(str(destination))
                        continue
                if isinstance(item, str) and item.startswith(("https://", "http://")):
                    artifacts.append(item)
            if not artifacts:
                raise RuntimeError("The image Space returned no usable image artifact")
            return {"status": "ok", "artifacts": artifacts}
        except asyncio.TimeoutError as exc:
            logger.warning("Image generation timed out")
            raise TimeoutError("Image generation exceeded the configured timeout") from exc
        except Exception as exc:
            logger.exception("Image generation failed")
            raise RuntimeError(f"Image generation failed: {exc}") from exc


media_generator = MediaGenerator()
