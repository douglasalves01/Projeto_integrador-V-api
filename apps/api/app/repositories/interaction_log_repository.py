import logging
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction_log import InteractionLog, InteractionType

logger = logging.getLogger(__name__)


class InteractionLogRepository:
    async def create(self, db: AsyncSession, log: InteractionLog) -> InteractionLog:
        db.add(log)
        await db.flush()
        await db.refresh(log)
        return log

    async def get_all_paginated(
        self,
        db: AsyncSession,
        page: int,
        page_size: int,
        user_id: Optional[UUID] = None,
        interaction_type: Optional[str] = None,
        video_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[InteractionLog], int]:
        query = select(InteractionLog)
        count_query = select(func.count(InteractionLog.id))

        if user_id:
            query = query.where(InteractionLog.user_id == user_id)
            count_query = count_query.where(InteractionLog.user_id == user_id)
        if interaction_type:
            query = query.where(InteractionLog.interaction_type == interaction_type)
            count_query = count_query.where(InteractionLog.interaction_type == interaction_type)
        if video_id:
            query = query.where(InteractionLog.video_id == video_id)
            count_query = count_query.where(InteractionLog.video_id == video_id)
        if start_date:
            query = query.where(InteractionLog.created_at >= start_date)
            count_query = count_query.where(InteractionLog.created_at >= start_date)
        if end_date:
            query = query.where(InteractionLog.created_at <= end_date)
            count_query = count_query.where(InteractionLog.created_at <= end_date)

        count_result = await db.execute(count_query)
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            query.offset(offset).limit(page_size).order_by(InteractionLog.created_at.desc())
        )
        logs = list(result.scalars().all())
        return logs, total

    async def get_user_interactions(
        self, db: AsyncSession, user_id: UUID
    ) -> List[InteractionLog]:
        result = await db.execute(
            select(InteractionLog)
            .where(InteractionLog.user_id == user_id)
            .order_by(InteractionLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_user_interactions(self, db: AsyncSession, user_id: UUID) -> int:
        result = await db.execute(
            select(func.count(InteractionLog.id)).where(InteractionLog.user_id == user_id)
        )
        return result.scalar()
