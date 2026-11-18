"""Lazy CPU-only llama.cpp inference adapter (Python binding or audited CLI runtime)."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from core.config import EngineConfig, config
from core.resource_optimizer import snapshot


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
    def cli_path() -> str | None:
        configured = os.getenv("ENGINE_LLAMA_CLI_PATH", "").strip()
        if configured:
            path = Path(configured).expanduser()
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which("llama-cli")

    @staticmethod
    def runtime_installed() -> bool:
        return importlib.util.find_spec("llama_cpp") is not None or LocalEngine.cli_path() is not None

    def is_ready(self) -> bool:
        return bool(self.settings.model_path and Path(self.settings.model_path).expanduser().is_file())

    def _check_resource_budget(self, model_path: Path) -> None:
        model_size_mb = model_path.stat().st_size / (1024 * 1024)
        available = snapshot(self.settings).memory_available_mb
        required_mb = model_size_mb + 1024
        if required_mb > self.settings.max_memory_mb:
            raise LocalEngineError(
                f"Model requires approximately {required_mb:.0f} MB including reserve; "
                f"configured limit is {self.settings.max_memory_mb} MB."
            )
        if available is not None and required_mb > available:
            raise LocalEngineError(
                f"Insufficient available memory: approximately {available} MB available, "
                f"{required_mb:.0f} MB required including reserve."
            )

    def _model_path(self) -> Path:
        model_path = Path(self.settings.model_path).expanduser()
        if not model_path.is_file():
            raise LocalEngineError("GGUF model not found. Provision a checksum-verified model first.")
        self._check_resource_budget(model_path)
        return model_path

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            model_path = self._model_path()
            factory = self._factory
            if factory is None:
                try:
                    from llama_cpp import Llama
                except ImportError as exc:
                    raise LocalEngineError("llama-cpp-python is not installed") from exc
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

    def _complete_cli(self, prompt: str, max_tokens: int | None) -> str:
        executable = self.cli_path()
        if not executable:
            raise LocalEngineError("No audited llama.cpp runtime is installed (llama-cli not found).")
        model_path = self._model_path()
        command = [
            executable, "--model", str(model_path), "--prompt", prompt,
            "--n-predict", str(max_tokens or self.settings.max_tokens),
            "--threads", str(self.settings.model_threads),
            "--ctx-size", str(self.settings.model_context),
            "--temp", str(self.settings.temperature),
            "--no-display-prompt", "--simple-io", "--no-warmup", "--no-conversation",
        ]
        try:
            result = subprocess.run(
                command, check=False, capture_output=True, text=True,
                timeout=max(5.0, float(self.settings.max_request_timeout)),
                env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
            )
        except subprocess.TimeoutExpired as exc:
            raise LocalEngineError("llama.cpp inference exceeded the request timeout") from exc
        except OSError as exc:
            raise LocalEngineError("unable to start llama.cpp CPU runtime") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown runtime error")[-1200:]
            raise LocalEngineError(f"llama.cpp exited with code {result.returncode}: {detail}")
        answer = result.stdout.strip()
        if not answer:
            raise LocalEngineError("llama.cpp returned an empty completion")
        return answer

    def complete(self, prompt: str, max_tokens: int | None = None) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must not be empty")
        if self._factory is not None or importlib.util.find_spec("llama_cpp") is not None:
            result = self._load().create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens or self.settings.max_tokens,
                temperature=self.settings.temperature,
            )
            try:
                content = result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LocalEngineError("llama.cpp returned an invalid completion payload") from exc
            if not isinstance(content, str) or not content.strip():
                raise LocalEngineError("llama.cpp returned non-text completion content")
            return content.strip()
        return self._complete_cli(prompt, max_tokens)
