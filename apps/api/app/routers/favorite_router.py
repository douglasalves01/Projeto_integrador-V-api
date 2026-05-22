import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.schemas.pagination import PaginatedResponse
from app.schemas.watch_session import WatchSessionResponse
from app.services.favorite_service import FavoriteService
from app.services.interaction_service import InteractionService

router = APIRouter()
favorite_service = FavoriteService()
interaction_service = InteractionService()


class FavoriteResponse:
    pass


from pydantic import BaseModel
import uuid
from datetime import datetime


class FavoriteItemResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    video_id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/{video_id}", response_model=FavoriteItemResponse, status_code=201)
async def add_favorite(
    video_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["user_id"])
    favorite = await favorite_service.add_favorite(db, user_id, video_id)

    # Log interaction
    await interaction_service.log_interaction_safe(
        db=db,
        user_id=user_id,
        interaction_type="FAVORITE",
        video_id=video_id,
    )

    return favorite


@router.delete("/{video_id}", status_code=204)
async def remove_favorite(
    video_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["user_id"])
    await favorite_service.remove_favorite(db, user_id, video_id)

    # Log interaction
    await interaction_service.log_interaction_safe(
        db=db,
        user_id=user_id,
        interaction_type="UNFAVORITE",
        video_id=video_id,
    )


@router.get("", response_model=PaginatedResponse[FavoriteItemResponse])
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["user_id"])
    favorites, total = await favorite_service.list_favorites(db, user_id, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=favorites, total=total, page=page, page_size=page_size, total_pages=total_pages
    )
