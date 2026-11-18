"""Small, dependency-free runtime configuration for ephemeral Actions runners."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class EngineConfig:
    model_path: str
    model_context: int
    model_threads: int
    model_batch: int
    max_tokens: int
    temperature: float
    max_memory_mb: int
    max_cpu_threads: int

    @classmethod
    def from_env(cls) -> "EngineConfig":
        cpu_count = max(1, os.cpu_count() or 1)
        try:
            temperature = float(os.getenv("ENGINE_TEMPERATURE", "0.2"))
        except ValueError:
            temperature = 0.2
        return cls(
            model_path=os.getenv("ENGINE_MODEL_PATH", "").strip(),
            model_context=_int_env("ENGINE_CONTEXT", 2048),
            model_threads=min(_int_env("ENGINE_THREADS", min(2, cpu_count)), cpu_count),
            model_batch=_int_env("ENGINE_BATCH", 128),
            max_tokens=_int_env("ENGINE_MAX_TOKENS", 512),
            temperature=min(2.0, max(0.0, temperature)),
            max_memory_mb=_int_env("ENGINE_MAX_MEMORY_MB", 12_288),
            max_cpu_threads=min(_int_env("ENGINE_MAX_CPU_THREADS", 2), cpu_count),
        )


config = EngineConfig.from_env()
