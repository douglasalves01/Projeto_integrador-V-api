from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.cache import ping_redis
from app.core.config import get_settings
from app.core.database import engine
from app.schemas.health import DependencyStatus, DetailedHealthResponse
from app.services.model_loader import model_loader

router = APIRouter(tags=["health"])
settings = get_settings()


def _check_mysql() -> DependencyStatus:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DependencyStatus(status="up")
    except Exception as exc:
        return DependencyStatus(status="down", detail=str(exc))


async def build_health_response(request: Request) -> DetailedHealthResponse:
    mysql_status = _check_mysql()
    redis_ok = await ping_redis()
    redis_status = DependencyStatus(status="up" if redis_ok else "down")

    models_loaded = model_loader.is_loaded
    model_version = model_loader.current_model_version

    overall = "healthy"
    if mysql_status.status != "up" or redis_status.status != "up":
        overall = "degraded"
    if not models_loaded:
        overall = "degraded"

    request.app.state.models_loaded = models_loaded
    request.app.state.model_version = model_version

    return DetailedHealthResponse(
        status=overall,
        service=settings.APP_NAME,
        model_version=model_version,
        models_loaded=models_loaded,
        mysql=mysql_status,
        redis=redis_status,
    )


@router.get("/health", response_model=DetailedHealthResponse)
async def health_check(request: Request) -> DetailedHealthResponse:
    """Service health including MySQL, Redis, and loaded model artifacts."""
    return await build_health_response(request)
