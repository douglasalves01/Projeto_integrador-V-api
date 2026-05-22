from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "vod-ai-service"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "*"

    # Database (Postgres compartilhado com a API do monorepo)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/streaming_db"
    DB_CONNECT_TIMEOUT: int = 5
    DB_POOL_TIMEOUT: int = 10

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    RECS_CACHE_TTL: int = 3600

    # Security
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    AI_API_KEY: str = "change-me-ai-api-key"
    ADMIN_API_KEY: str = ""  # defaults to AI_API_KEY when empty

    # ML models (classic TF-IDF + ALS)
    MODEL_PATH: str = "/app/models"
    AI_MODEL_VERSION: str = "0.0.0"

    # Observability
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "vod-ai-service"
    OTEL_EXPORTER_ENDPOINT: str = "http://localhost:4318/v1/traces"

    # LLM models (VodRec-Transformer + VodChat)
    VODREC_MODEL_PATH: str = "models/vodrec/model.pt"
    VODREC_VOCAB_PATH: str = "models/vodrec/vocab.json"
    VODCHAT_ADAPTER_PATH: str = "models/vodchat/vodchat-lora-final"
    VODCHAT_BASE_MODEL: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    VODCHAT_GGUF_PATH: str | None = None
    LLM_ENABLED: bool = True
    VODCHAT_ENABLED: bool = True

    @property
    def admin_api_key(self) -> str:
        return self.ADMIN_API_KEY or self.AI_API_KEY

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
