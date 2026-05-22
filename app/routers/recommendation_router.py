import math
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.pagination import PaginatedResponse
from app.schemas.recommendation import RecommendationResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter()
recommendation_service = RecommendationService()


@router.get("/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(current_user["user_id"])
    recommendations = await recommendation_service.get_recommendations(db, user_id)
    return recommendations


@router.get("/admin/recommendations", response_model=PaginatedResponse[RecommendationResponse])
async def list_all_recommendations(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    recs, total = await recommendation_service.get_all_recommendations_paginated(db, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=recs, total=total, page=page, page_size=page_size, total_pages=total_pages
    )
