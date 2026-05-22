from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ensure_user_access, get_current_user
from app.schemas.recommendation import RecommendationResponse
from app.services.model_loader import model_loader
from app.services.recommendation_service import get_recommendations
from app.services.user_service import get_user_or_raise

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/{user_id}", response_model=RecommendationResponse)
async def get_user_recommendations(
    user_id: int,
    k: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    """Return personalized recommendations with Redis caching."""
    ensure_user_access(current_user, user_id)
    get_user_or_raise(db, user_id)

    if not model_loader.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recommendation models are not loaded",
        )

    try:
        return await get_recommendations(db=db, user_id=user_id, k=k)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
