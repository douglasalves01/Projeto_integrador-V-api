import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.schemas.pagination import PaginatedResponse
from app.schemas.watch_session import WatchSessionUpdate, WatchSessionResponse
from app.services.watch_session_service import WatchSessionService
from app.services.interaction_service import InteractionService

router = APIRouter()
watch_session_service = WatchSessionService()
interaction_service = InteractionService()


@router.get("/watch-history", response_model=PaginatedResponse[WatchSessionResponse])
async def get_watch_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["user_id"])
    sessions, total = await watch_session_service.get_user_history(db, user_id, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=sessions, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.patch("/watch-sessions/{session_id}", response_model=WatchSessionResponse)
async def update_watch_session(
    session_id: UUID,
    data: WatchSessionUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["user_id"])
    session = await watch_session_service.update_session(
        db, session_id, data.watch_time_seconds, user_id
    )

    # Log WATCH interaction
    await interaction_service.log_interaction_safe(
        db=db,
        user_id=user_id,
        interaction_type="WATCH",
        video_id=session.video_id,
        metadata={"watch_time_seconds": data.watch_time_seconds},
    )

    # Invalida cache de recomendacoes — novo dado de assistencia pode alterar ranking
    from app.core.cache import invalidate_recommendations
    await invalidate_recommendations(str(user_id))

    return session
