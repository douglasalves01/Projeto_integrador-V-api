import logging
from typing import Optional, List, Tuple, Any, Dict
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction_log import InteractionLog, InteractionType
from app.repositories.interaction_log_repository import InteractionLogRepository

logger = logging.getLogger(__name__)


class InteractionService:
    def __init__(self):
        self.interaction_repo = InteractionLogRepository()

    async def log_interaction_safe(
        self,
        db: AsyncSession,
        user_id: UUID,
        interaction_type: str,
        video_id: Optional[UUID] = None,
        search_query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Fire-and-forget interaction logging. Failures do not propagate."""
        try:
            log = InteractionLog(
                user_id=user_id,
                video_id=video_id,
                interaction_type=InteractionType(interaction_type),
                search_query=search_query,
                metadata_=metadata,
            )
            await self.interaction_repo.create(db, log)
        except Exception as e:
            logger.error(f"Failed to persist interaction log: {e}")

    async def list_interactions(
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
        return await self.interaction_repo.get_all_paginated(
            db, page, page_size, user_id, interaction_type, video_id, start_date, end_date
        )
