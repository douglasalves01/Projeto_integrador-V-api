from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watch_session import WatchSession


class WatchSessionRepository:
    async def create(self, db: AsyncSession, session: WatchSession) -> WatchSession:
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    async def get_by_id(self, db: AsyncSession, session_id: UUID) -> Optional[WatchSession]:
        result = await db.execute(
            select(WatchSession).where(WatchSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def update(self, db: AsyncSession, session: WatchSession) -> WatchSession:
        await db.flush()
        await db.refresh(session)
        return session

    async def get_user_history_paginated(
        self, db: AsyncSession, user_id: UUID, page: int, page_size: int
    ) -> Tuple[List[WatchSession], int]:
        count_result = await db.execute(
            select(func.count(WatchSession.id)).where(WatchSession.user_id == user_id)
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(WatchSession)
            .where(WatchSession.user_id == user_id)
            .offset(offset)
            .limit(page_size)
            .order_by(WatchSession.started_at.desc())
        )
        sessions = list(result.scalars().all())
        return sessions, total

    async def get_completed_video_ids_for_user(
        self, db: AsyncSession, user_id: UUID
    ) -> List[UUID]:
        result = await db.execute(
            select(WatchSession.video_id).where(
                WatchSession.user_id == user_id,
                WatchSession.completed == True,
            ).distinct()
        )
        return [row[0] for row in result.all()]
