from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.video import Video
from app.models.video_genre import video_genre
from app.models.video_category import video_category
from app.models.watch_session import WatchSession


class VideoRepository:
    def _base_query(self):
        return select(Video).options(
            selectinload(Video.genres),
            selectinload(Video.categories),
        )

    async def create(self, db: AsyncSession, video: Video) -> Video:
        db.add(video)
        await db.flush()
        await db.refresh(video, attribute_names=["genres", "categories"])
        return video

    async def get_by_id(self, db: AsyncSession, video_id: UUID) -> Optional[Video]:
        result = await db.execute(
            self._base_query().where(Video.id == video_id)
        )
        return result.scalar_one_or_none()

    async def get_all_paginated(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[Video], int]:
        count_result = await db.execute(select(func.count(Video.id)))
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            self._base_query().offset(offset).limit(page_size).order_by(Video.created_at.desc())
        )
        videos = list(result.scalars().unique().all())
        return videos, total

    async def search_by_title(
        self, db: AsyncSession, term: str, page: int, page_size: int
    ) -> Tuple[List[Video], int]:
        base = select(Video).where(Video.title.ilike(f"%{term}%"))
        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            self._base_query().where(Video.title.ilike(f"%{term}%"))
            .offset(offset).limit(page_size).order_by(Video.created_at.desc())
        )
        videos = list(result.scalars().unique().all())
        return videos, total

    async def filter_by_genre(
        self, db: AsyncSession, genre_id: UUID, page: int, page_size: int
    ) -> Tuple[List[Video], int]:
        base = (
            select(Video)
            .join(video_genre, Video.id == video_genre.c.video_id)
            .where(video_genre.c.genre_id == genre_id)
        )
        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            self._base_query()
            .join(video_genre, Video.id == video_genre.c.video_id)
            .where(video_genre.c.genre_id == genre_id)
            .offset(offset).limit(page_size).order_by(Video.created_at.desc())
        )
        videos = list(result.scalars().unique().all())
        return videos, total

    async def filter_by_category(
        self, db: AsyncSession, category_id: UUID, page: int, page_size: int
    ) -> Tuple[List[Video], int]:
        base = (
            select(Video)
            .join(video_category, Video.id == video_category.c.video_id)
            .where(video_category.c.category_id == category_id)
        )
        count_result = await db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            self._base_query()
            .join(video_category, Video.id == video_category.c.video_id)
            .where(video_category.c.category_id == category_id)
            .offset(offset).limit(page_size).order_by(Video.created_at.desc())
        )
        videos = list(result.scalars().unique().all())
        return videos, total

    async def update(self, db: AsyncSession, video: Video) -> Video:
        await db.flush()
        await db.refresh(video, attribute_names=["genres", "categories"])
        return video

    async def delete(self, db: AsyncSession, video: Video) -> None:
        await db.delete(video)
        await db.flush()

    async def get_popular_videos(
        self, db: AsyncSession, limit: int = 10, exclude_video_ids: List[UUID] = None
    ) -> List[Video]:
        query = (
            self._base_query()
            .outerjoin(WatchSession, Video.id == WatchSession.video_id)
            .group_by(Video.id)
            .order_by(func.count(WatchSession.id).desc())
            .limit(limit)
        )
        if exclude_video_ids:
            query = query.where(Video.id.notin_(exclude_video_ids))

        result = await db.execute(query)
        return list(result.scalars().unique().all())
