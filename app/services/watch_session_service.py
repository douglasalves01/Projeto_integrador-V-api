from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watch_session import WatchSession
from app.repositories.watch_session_repository import WatchSessionRepository
from app.repositories.video_repository import VideoRepository


class WatchSessionService:
    def __init__(self):
        self.session_repo = WatchSessionRepository()
        self.video_repo = VideoRepository()

    async def create_session(self, db: AsyncSession, user_id: UUID, video_id: UUID) -> WatchSession:
        session = WatchSession(user_id=user_id, video_id=video_id)
        return await self.session_repo.create(db, session)

    async def update_session(
        self, db: AsyncSession, session_id: UUID, watch_time_seconds: int, user_id: UUID
    ) -> WatchSession:
        session = await self.session_repo.get_by_id(db, session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watch session not found",
            )

        if str(session.user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this session",
            )

        # Get video duration
        video = await self.video_repo.get_by_id(db, session.video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )

        duration = video.duration_seconds
        session.watch_time_seconds = watch_time_seconds
        session.percentage_watched = watch_time_seconds / duration if duration > 0 else 0.0
        session.completed = session.percentage_watched >= 0.9
        session.abandoned = session.percentage_watched < 0.1

        return await self.session_repo.update(db, session)

    async def get_user_history(
        self, db: AsyncSession, user_id: UUID, page: int, page_size: int
    ) -> Tuple[List[WatchSession], int]:
        return await self.session_repo.get_user_history_paginated(db, user_id, page, page_size)
