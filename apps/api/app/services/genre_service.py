from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.genre import Genre
from app.repositories.genre_repository import GenreRepository
from app.schemas.genre import GenreCreate, GenreUpdate


class GenreService:
    def __init__(self):
        self.genre_repo = GenreRepository()

    async def create_genre(self, db: AsyncSession, data: GenreCreate) -> Genre:
        existing = await self.genre_repo.get_by_name(db, data.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Genre with this name already exists",
            )
        genre = Genre(name=data.name)
        return await self.genre_repo.create(db, genre)

    async def get_genre(self, db: AsyncSession, genre_id: UUID) -> Genre:
        genre = await self.genre_repo.get_by_id(db, genre_id)
        if not genre:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Genre not found",
            )
        return genre

    async def list_genres(self, db: AsyncSession, page: int, page_size: int) -> Tuple[List[Genre], int]:
        return await self.genre_repo.get_all_paginated(db, page, page_size)

    async def update_genre(self, db: AsyncSession, genre_id: UUID, data: GenreUpdate) -> Genre:
        genre = await self.genre_repo.get_by_id(db, genre_id)
        if not genre:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Genre not found",
            )

        if data.name is not None:
            existing = await self.genre_repo.get_by_name(db, data.name)
            if existing and existing.id != genre_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Genre with this name already exists",
                )
            genre.name = data.name

        return await self.genre_repo.update(db, genre)

    async def delete_genre(self, db: AsyncSession, genre_id: UUID) -> None:
        genre = await self.genre_repo.get_by_id(db, genre_id)
        if not genre:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Genre not found",
            )

        in_use = await self.genre_repo.check_in_use(db, genre_id)
        if in_use:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Genre is in use and cannot be deleted",
            )

        await self.genre_repo.delete(db, genre)
