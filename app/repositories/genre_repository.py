from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.genre import Genre
from app.models.video_genre import video_genre


class GenreRepository:
    async def create(self, db: AsyncSession, genre: Genre) -> Genre:
        db.add(genre)
        await db.flush()
        await db.refresh(genre)
        return genre

    async def get_by_id(self, db: AsyncSession, genre_id: UUID) -> Optional[Genre]:
        result = await db.execute(select(Genre).where(Genre.id == genre_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[Genre]:
        result = await db.execute(select(Genre).where(Genre.name == name))
        return result.scalar_one_or_none()

    async def get_all(self, db: AsyncSession) -> List[Genre]:
        result = await db.execute(select(Genre).order_by(Genre.name))
        return list(result.scalars().all())

    async def get_all_paginated(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[Genre], int]:
        count_result = await db.execute(select(func.count(Genre.id)))
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(Genre).offset(offset).limit(page_size).order_by(Genre.name)
        )
        genres = list(result.scalars().all())
        return genres, total

    async def update(self, db: AsyncSession, genre: Genre) -> Genre:
        await db.flush()
        await db.refresh(genre)
        return genre

    async def delete(self, db: AsyncSession, genre: Genre) -> None:
        await db.delete(genre)
        await db.flush()

    async def check_in_use(self, db: AsyncSession, genre_id: UUID) -> bool:
        result = await db.execute(
            select(func.count()).select_from(video_genre).where(
                video_genre.c.genre_id == genre_id
            )
        )
        count = result.scalar()
        return count > 0
