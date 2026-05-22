from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.report import (
    UsageReport,
    RankedVideoReport,
    AbandonmentVideoReport,
    RankedGenreReport,
    RankedUserReport,
)
from app.services.report_service import ReportService

router = APIRouter()
report_service = ReportService()


@router.get("/usage", response_model=UsageReport)
async def get_usage_report(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_usage_report(db, start_date, end_date)


@router.get("/most-watched", response_model=List[RankedVideoReport])
async def get_most_watched(
    limit: int = Query(10, ge=1, le=100),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_most_watched(db, limit, start_date, end_date)


@router.get("/abandonment", response_model=List[AbandonmentVideoReport])
async def get_highest_abandonment(
    limit: int = Query(10, ge=1, le=100),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_highest_abandonment(db, limit, start_date, end_date)


@router.get("/popular-genres", response_model=List[RankedGenreReport])
async def get_popular_genres(
    limit: int = Query(10, ge=1, le=100),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_popular_genres(db, limit, start_date, end_date)


@router.get("/active-users", response_model=List[RankedUserReport])
async def get_most_active_users(
    limit: int = Query(10, ge=1, le=100),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_most_active_users(db, limit, start_date, end_date)
