"""Shared FastAPI dependencies."""

from fastapi import Header, HTTPException, status

from app.core.config import get_settings
from app.models.hybrid import HybridRecommender
from app.services.model_loader import model_loader

settings = get_settings()


def get_hybrid_recommender() -> HybridRecommender:
    if not model_loader.is_loaded or model_loader.hybrid is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recommendation models are not loaded",
        )
    return model_loader.hybrid


async def verify_ai_api_key(
    x_ai_api_key: str = Header(..., alias="X-AI-API-Key"),
) -> None:
    if x_ai_api_key != settings.AI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )


async def verify_admin_api_key(
    x_ai_api_key: str = Header(..., alias="X-AI-API-Key"),
) -> None:
    if x_ai_api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
