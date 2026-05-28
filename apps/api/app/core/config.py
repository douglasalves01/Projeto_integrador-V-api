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

    # Chat — anexar sugestões de vídeo (busca semântica / textual)
    CHAT_ATTACH_VIDEOS: bool = True
    CHAT_VIDEO_SUGGESTIONS_LIMIT: int = 5
    CHAT_VIDEO_CANDIDATE_LIMIT: int = 24
    CHAT_SEMANTIC_MAX_DISTANCE: float = 0.58
    CHAT_REQUIRE_TOPIC_KEYWORD_MATCH: bool = True
    CHAT_SEMANTIC_SEARCH_ON_CHAT: bool = True
    # Com videos[] preenchido, reply vem do catalogo (nao do VodChat alucinado).
    CHAT_PREFER_CATALOG_REPLY: bool = True

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
