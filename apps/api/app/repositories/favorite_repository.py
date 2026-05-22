from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.favorite import Favorite


class FavoriteRepository:
    async def add_favorite(self, db: AsyncSession, favorite: Favorite) -> Favorite:
        db.add(favorite)
        await db.flush()
        await db.refresh(favorite)
        return favorite

    async def remove_favorite(self, db: AsyncSession, user_id: UUID, video_id: UUID) -> bool:
        result = await db.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.video_id == video_id,
            )
        )
        favorite = result.scalar_one_or_none()
        if favorite:
            await db.delete(favorite)
            await db.flush()
            return True
        return False

    async def get_user_favorites_paginated(
        self, db: AsyncSession, user_id: UUID, page: int, page_size: int
    ) -> Tuple[List[Favorite], int]:
        count_result = await db.execute(
            select(func.count(Favorite.id)).where(Favorite.user_id == user_id)
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .offset(offset)
            .limit(page_size)
            .order_by(Favorite.created_at.desc())
        )
        favorites = list(result.scalars().all())
        return favorites, total

    async def check_exists(self, db: AsyncSession, user_id: UUID, video_id: UUID) -> bool:
        result = await db.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.video_id == video_id,
            )
        )
        return result.scalar_one_or_none() is not None
