from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.orm import Session

from app.core.cache import invalidate_user_recs_cache
from app.core.database import get_db
from app.core.exceptions import ResourceNotFoundError
from app.core.security import ensure_user_access, get_current_user
from app.schemas.profile import UserProfileResponse
from app.schemas.recommendation import InteractionUpdate
from app.services.recommendation_service import update_user_profile
from app.services.user_service import get_user_or_raise

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/{user_id}/update", response_model=UserProfileResponse)
async def update_profile(
    user_id: int,
    interaction: InteractionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UserProfileResponse:
    """Apply an interaction update and refresh the user's AI profile."""
    ensure_user_access(current_user, user_id)
    get_user_or_raise(db, user_id)

    try:
        profile = update_user_profile(db, user_id, interaction)
    except ValueError as exc:
        raise ResourceNotFoundError("Content", interaction.content_id) from exc

    deleted_keys = await invalidate_user_recs_cache(user_id)
    logger.info("profile updated", user_id=user_id, cache_keys_deleted=deleted_keys)

    return UserProfileResponse(
        user_id=profile.user_id,
        genre_weights=profile.genre_weights,
        category_weights=profile.category_weights,
        total_views=profile.total_views,
        last_updated=profile.last_updated,
    )
