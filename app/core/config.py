from pydantic_settings import BaseSettings


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

    # AI integration
    AI_SERVICE_URL: str = "http://localhost:8002/api/v1"
    AI_SERVICE_API_KEY: str = ""
    AI_ENABLED: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
