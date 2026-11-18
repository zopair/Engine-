from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Autonomous AI Engine"
    environment: str = "production"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 7860

    database_url: str = "sqlite:///./data/engine.db"
    database_path: str = "./data/engine.db"
    huey_database_path: str = "./data/huey.db"

    # Local GGUF inference is lazy-loaded and strictly CPU-only.
    local_model_path: str = ""
    local_model_n_ctx: int = 4096
    local_model_n_threads: int = 2
    local_model_n_batch: int = 256

    groq_api_key: str = ""
    groq_models: str = "llama-3.1-8b-instant,llama-3.3-70b-versatile"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openrouter_api_key: str = ""
    openrouter_free_models: str = "openrouter/free"
    hf_token: str = ""

    searxng_url: str = "https://searx.be"
    crawl_timeout_seconds: float = 25.0
    hf_image_space: str = "black-forest-labs/FLUX.1-schnell"
    hf_image_api_name: str = "/infer"
    media_output_dir: str = "./data/generated"
    whisper_model: str = "tiny"
    whisper_cpu_threads: int = 2
    piper_executable: str = "piper"
    piper_model_path: str = "./models/en_US-lessac-medium.onnx"
    piper_timeout_seconds: float = 30.0
    mem0_enabled: bool = False

    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "ai-engine-backups"
    r2_region: str = "auto"

    cors_origins: str = "*"
    api_key: str = ""
    max_request_timeout: float = 45.0
    max_context_messages: int = 12

    # Semantic indexing is opt-in to avoid downloading models at startup.
    semantic_cache_enabled: bool = False
    embedding_model: str = "Xenova/all-MiniLM-L6-v2"
    semantic_similarity_threshold: float = 0.92
    embedding_download_timeout: float = 60.0

    dspy_model: str = ""


settings = Settings()
