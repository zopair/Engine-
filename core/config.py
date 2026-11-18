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
    model_release_url: str
    model_sha256: str
    model_context: int
    model_threads: int
    model_batch: int
    max_tokens: int
    temperature: float
    max_memory_mb: int
    max_cpu_threads: int
    database_path: str = "./data/engine.db"
    huey_database_path: str = "./data/huey.db"
    groq_api_key: str = ""
    groq_models: str = ""
    gemini_api_key: str = ""
    gemini_model: str = ""
    openrouter_api_key: str = ""
    openrouter_free_models: str = ""
    hf_token: str = ""
    searxng_url: str = ""
    crawl_timeout_seconds: float = 15.0
    mem0_enabled: bool = False
    max_request_timeout: float = 30.0
    semantic_cache_enabled: bool = False
    embedding_model: str = ""
    semantic_similarity_threshold: float = 0.92
    embedding_download_timeout: float = 30.0
    dspy_model: str = ""
    api_key: str = ""

    @classmethod
    def from_env(cls) -> "EngineConfig":
        cpu_count = max(1, os.cpu_count() or 1)
        try:
            temperature = float(os.getenv("ENGINE_TEMPERATURE", "0.2"))
        except ValueError:
            temperature = 0.2
        try:
            crawl_timeout = float(os.getenv("CRAWL_TIMEOUT_SECONDS", "15"))
            request_timeout = float(os.getenv("ENGINE_REQUEST_TIMEOUT", "30"))
            similarity = float(os.getenv("SEMANTIC_SIMILARITY_THRESHOLD", "0.92"))
            embedding_timeout = float(os.getenv("EMBEDDING_DOWNLOAD_TIMEOUT", "30"))
        except ValueError:
            crawl_timeout, request_timeout, similarity, embedding_timeout = 15.0, 30.0, 0.92, 30.0
        return cls(
            model_path=os.getenv("ENGINE_MODEL_PATH", "~/.cache/engine/models/qwen2.5-0.5b-instruct-q4_k_m.gguf").strip(),
            model_release_url=os.getenv("ENGINE_MODEL_RELEASE_URL", "https://github.com/zopair/Engine-/releases/download/models-v1/qwen2.5-0.5b-instruct-q4_k_m.gguf").strip(),
            model_sha256=os.getenv("ENGINE_MODEL_SHA256", "").strip(),
            model_context=_int_env("ENGINE_CONTEXT", 2048),
            model_threads=min(_int_env("ENGINE_THREADS", min(2, cpu_count)), cpu_count),
            model_batch=_int_env("ENGINE_BATCH", 128),
            max_tokens=_int_env("ENGINE_MAX_TOKENS", 512),
            temperature=min(2.0, max(0.0, temperature)),
            max_memory_mb=_int_env("ENGINE_MAX_MEMORY_MB", 12_288),
            max_cpu_threads=min(_int_env("ENGINE_MAX_CPU_THREADS", 2), cpu_count),
            database_path=os.getenv("ENGINE_DATABASE_PATH", "./data/engine.db"),
            huey_database_path=os.getenv("ENGINE_HUEY_DATABASE_PATH", "./data/huey.db"),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_models=os.getenv("GROQ_MODELS", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", ""),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            openrouter_free_models=os.getenv("OPENROUTER_FREE_MODELS", ""),
            hf_token=os.getenv("HF_TOKEN", ""),
            searxng_url=os.getenv("SEARXNG_URL", ""),
            crawl_timeout_seconds=crawl_timeout,
            mem0_enabled=os.getenv("MEM0_ENABLED", "false").lower() == "true",
            max_request_timeout=request_timeout,
            semantic_cache_enabled=os.getenv("SEMANTIC_CACHE_ENABLED", "false").lower() == "true",
            embedding_model=os.getenv("EMBEDDING_MODEL", ""),
            semantic_similarity_threshold=similarity,
            embedding_download_timeout=embedding_timeout,
            dspy_model=os.getenv("DSPY_MODEL", ""),
            api_key=os.getenv("ENGINE_API_KEY", ""),
        )


config = EngineConfig.from_env()
# Compatibility alias for legacy modules during the staged migration.
settings = config
