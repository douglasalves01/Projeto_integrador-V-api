import math
from uuid import UUID
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.interaction_log import InteractionLogResponse
from app.schemas.pagination import PaginatedResponse
from app.services.interaction_service import InteractionService

router = APIRouter()
interaction_service = InteractionService()


@router.get("/interactions", response_model=PaginatedResponse[InteractionLogResponse])
async def list_interactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    user_id: Optional[UUID] = Query(None),
    interaction_type: Optional[str] = Query(None),
    video_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    logs, total = await interaction_service.list_interactions(
        db, page, page_size, user_id, interaction_type, video_id, start_date, end_date
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=logs, total=total, page=page, page_size=page_size, total_pages=total_pages
    )
