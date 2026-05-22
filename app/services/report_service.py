from datetime import datetime
from typing import Optional, List, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction_log import InteractionLog
from app.models.user import User
from app.models.video import Video
from app.models.watch_session import WatchSession
from app.models.video_genre import video_genre
from app.models.genre import Genre
from app.schemas.report import (
    UsageReport,
    RankedVideoReport,
    AbandonmentVideoReport,
    RankedGenreReport,
    RankedUserReport,
)


class ReportService:
    def _validate_date_range(self, start_date: Optional[datetime], end_date: Optional[datetime]):
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date range: start_date must be before end_date",
            )

    async def get_usage_report(
        self, db: AsyncSession, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> UsageReport:
        self._validate_date_range(start_date, end_date)

        # Total users
        total_users_result = await db.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar()

        # Watch sessions query with date filter
        ws_query = select(WatchSession)
        if start_date:
            ws_query = ws_query.where(WatchSession.started_at >= start_date)
        if end_date:
            ws_query = ws_query.where(WatchSession.started_at <= end_date)

        # Active users (users with at least 1 watch session in range)
        active_query = select(func.count(func.distinct(WatchSession.user_id)))
        if start_date:
            active_query = active_query.where(WatchSession.started_at >= start_date)
        if end_date:
            active_query = active_query.where(WatchSession.started_at <= end_date)
        active_result = await db.execute(active_query)
        active_users = active_result.scalar()

        # Total watch sessions
        total_sessions_query = select(func.count(WatchSession.id))
        if start_date:
            total_sessions_query = total_sessions_query.where(WatchSession.started_at >= start_date)
        if end_date:
            total_sessions_query = total_sessions_query.where(WatchSession.started_at <= end_date)
        total_sessions_result = await db.execute(total_sessions_query)
        total_sessions = total_sessions_result.scalar()

        # Average watch time
        avg_query = select(func.avg(WatchSession.watch_time_seconds))
        if start_date:
            avg_query = avg_query.where(WatchSession.started_at >= start_date)
        if end_date:
            avg_query = avg_query.where(WatchSession.started_at <= end_date)
        avg_result = await db.execute(avg_query)
        avg_watch_time = avg_result.scalar() or 0.0

        return UsageReport(
            total_users=total_users,
            active_users=active_users,
            total_watch_sessions=total_sessions,
            average_watch_time_seconds=float(avg_watch_time),
        )

    async def get_most_watched(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[RankedVideoReport]:
        self._validate_date_range(start_date, end_date)

        query = (
            select(
                WatchSession.video_id,
                Video.title,
                func.count(WatchSession.id).label("watch_count"),
            )
            .join(Video, WatchSession.video_id == Video.id)
            .group_by(WatchSession.video_id, Video.title)
            .order_by(func.count(WatchSession.id).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            RankedVideoReport(video_id=row[0], title=row[1], count=row[2])
            for row in rows
        ]

    async def get_highest_abandonment(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[AbandonmentVideoReport]:
        self._validate_date_range(start_date, end_date)

        # Calculate abandonment rate per video
        abandoned_count = func.sum(case((WatchSession.abandoned == True, 1), else_=0))
        total_count = func.count(WatchSession.id)

        query = (
            select(
                WatchSession.video_id,
                Video.title,
                (abandoned_count * 1.0 / total_count).label("abandonment_rate"),
            )
            .join(Video, WatchSession.video_id == Video.id)
            .group_by(WatchSession.video_id, Video.title)
            .having(total_count > 0)
            .order_by((abandoned_count * 1.0 / total_count).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            AbandonmentVideoReport(video_id=row[0], title=row[1], abandonment_rate=float(row[2]))
            for row in rows
        ]

    async def get_popular_genres(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[RankedGenreReport]:
        self._validate_date_range(start_date, end_date)

        query = (
            select(
                Genre.id,
                Genre.name,
                func.sum(WatchSession.watch_time_seconds).label("total_watch_time"),
            )
            .join(video_genre, Genre.id == video_genre.c.genre_id)
            .join(WatchSession, video_genre.c.video_id == WatchSession.video_id)
            .group_by(Genre.id, Genre.name)
            .order_by(func.sum(WatchSession.watch_time_seconds).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            RankedGenreReport(genre_id=row[0], name=row[1], total_watch_time_seconds=int(row[2]))
            for row in rows
        ]

    async def get_most_active_users(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[RankedUserReport]:
        self._validate_date_range(start_date, end_date)

        query = (
            select(
                User.id,
                User.name,
                User.email,
                func.count(InteractionLog.id).label("interaction_count"),
            )
            .join(InteractionLog, User.id == InteractionLog.user_id)
            .group_by(User.id, User.name, User.email)
            .order_by(func.count(InteractionLog.id).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(InteractionLog.created_at >= start_date)
        if end_date:
            query = query.where(InteractionLog.created_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            RankedUserReport(user_id=row[0], name=row[1], email=row[2], interaction_count=row[3])
            for row in rows
        ]
