import math
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.pagination import PaginatedResponse
from app.schemas.video import VideoCreate, VideoUpdate, VideoResponse
from app.services.video_service import VideoService
from app.services.watch_session_service import WatchSessionService
from app.services.interaction_service import InteractionService

router = APIRouter()
video_service = VideoService()
watch_session_service = WatchSessionService()
interaction_service = InteractionService()


@router.post("", response_model=VideoResponse, status_code=201)
async def create_video(
    data: VideoCreate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await video_service.create_video(db, data)


@router.get("", response_model=PaginatedResponse[VideoResponse])
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    videos, total = await video_service.list_videos(db, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=videos, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get("/search", response_model=PaginatedResponse[VideoResponse])
async def search_videos(
    q: Optional[str] = Query(None),
    genre_id: Optional[UUID] = Query(None),
    category_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    videos, total = await video_service.search_videos(
        db, query=q, genre_id=genre_id, category_id=category_id, page=page, page_size=page_size
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    # Log search interaction
    if q:
        await interaction_service.log_interaction_safe(
            db=db,
            user_id=UUID(current_user["user_id"]),
            interaction_type="SEARCH",
            search_query=q,
            metadata={"genre_id": str(genre_id) if genre_id else None, "category_id": str(category_id) if category_id else None},
        )

    return PaginatedResponse(
        items=videos, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get("/{video_id}/watch", response_model=VideoResponse)
async def watch_video(
    video_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    video = await video_service.get_video_for_watch(db, video_id)

    # Create watch session
    user_id = UUID(current_user["user_id"])
    await watch_session_service.create_session(db, user_id, video_id)

    # Log interaction
    await interaction_service.log_interaction_safe(
        db=db,
        user_id=user_id,
        interaction_type="CLICK",
        video_id=video_id,
    )

    return video


@router.put("/{video_id}", response_model=VideoResponse)
async def update_video(
    video_id: UUID,
    data: VideoUpdate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await video_service.update_video(db, video_id, data)


@router.delete("/{video_id}", status_code=204)
async def delete_video(
    video_id: UUID,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await video_service.delete_video(db, video_id)
