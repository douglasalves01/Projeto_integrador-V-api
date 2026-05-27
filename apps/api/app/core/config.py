from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    paths: list[str] = []
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            paths.append(str(candidate))
    paths.append(".env")
    return tuple(dict.fromkeys(paths))


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/streaming_db"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "streaming_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"

    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"

    # App
    APP_NAME: str = "Streaming Recommendation API"
    DEBUG: bool = False

    # Cache Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    RECS_CACHE_TTL: int = 300  # 5 minutos

    # Integracao com o servico de IA (apps/ai do monorepo)
    AI_SERVICE_URL: str = "http://ai:8000/api/v1"
    AI_SERVICE_API_KEY: str = ""
    AI_ENABLED: bool = True
    SEMANTIC_SEARCH_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
