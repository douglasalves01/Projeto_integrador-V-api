from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.favorite import Favorite
from app.repositories.favorite_repository import FavoriteRepository
from app.repositories.video_repository import VideoRepository


class FavoriteService:
    def __init__(self):
        self.favorite_repo = FavoriteRepository()
        self.video_repo = VideoRepository()

    async def add_favorite(self, db: AsyncSession, user_id: UUID, video_id: UUID) -> Favorite:
        # Check video exists
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )

        # Check if already favorited
        exists = await self.favorite_repo.check_exists(db, user_id, video_id)
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Video already favorited",
            )

        favorite = Favorite(user_id=user_id, video_id=video_id)
        return await self.favorite_repo.add_favorite(db, favorite)

    async def remove_favorite(self, db: AsyncSession, user_id: UUID, video_id: UUID) -> None:
        removed = await self.favorite_repo.remove_favorite(db, user_id, video_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Favorite not found",
            )

    async def list_favorites(
        self, db: AsyncSession, user_id: UUID, page: int, page_size: int
    ) -> Tuple[List[Favorite], int]:
        return await self.favorite_repo.get_user_favorites_paginated(db, user_id, page, page_size)
