from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Autonomous AI Engine"
    environment: str = "production"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 7860

    database_url: str = "sqlite:///./data/engine.db"
    database_path: str = "./data/engine.db"
    huey_database_path: str = "./data/huey.db"

    groq_api_key: str = ""
    groq_models: str = "llama-3.1-8b-instant,llama-3.3-70b-versatile"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openrouter_api_key: str = ""
    openrouter_free_models: str = "openrouter/free"
    hf_token: str = ""

    searxng_url: str = "https://searx.be"
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "ai-engine-backups"
    r2_region: str = "auto"

    cors_origins: str = "*"
    api_key: str = ""
    max_request_timeout: float = 45.0
    max_context_messages: int = 12

    semantic_cache_enabled: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    semantic_similarity_threshold: float = 0.92


settings = Settings()
