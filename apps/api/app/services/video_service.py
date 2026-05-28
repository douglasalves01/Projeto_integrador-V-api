from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video import Video
from app.repositories.video_repository import VideoRepository
from app.repositories.genre_repository import GenreRepository
from app.repositories.category_repository import CategoryRepository
from app.schemas.video import VideoCreate, VideoUpdate


class VideoService:
    def __init__(self):
        self.video_repo = VideoRepository()
        self.genre_repo = GenreRepository()
        self.category_repo = CategoryRepository()

    async def create_video(self, db: AsyncSession, data: VideoCreate) -> Video:
        # Validate genres exist
        genres = []
        for genre_id in data.genre_ids:
            genre = await self.genre_repo.get_by_id(db, genre_id)
            if not genre:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Genre {genre_id} not found",
                )
            genres.append(genre)

        # Validate categories exist
        categories = []
        for category_id in data.category_ids:
            category = await self.category_repo.get_by_id(db, category_id)
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Category {category_id} not found",
                )
            categories.append(category)

        video = Video(
            title=data.title,
            description=data.description,
            url=data.url,
            duration_seconds=data.duration_seconds,
            release_date=data.release_date,
            age_rating=data.age_rating,
        )
        video.genres = genres
        video.categories = categories

        return await self.video_repo.create(db, video)

    async def update_video(self, db: AsyncSession, video_id: UUID, data: VideoUpdate) -> Video:
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )

        if data.title is not None:
            video.title = data.title
        if data.description is not None:
            video.description = data.description
        if data.url is not None:
            video.url = data.url
        if data.duration_seconds is not None:
            video.duration_seconds = data.duration_seconds
        if data.release_date is not None:
            video.release_date = data.release_date
        if data.age_rating is not None:
            video.age_rating = data.age_rating

        if data.genre_ids is not None:
            genres = []
            for genre_id in data.genre_ids:
                genre = await self.genre_repo.get_by_id(db, genre_id)
                if not genre:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Genre {genre_id} not found",
                    )
                genres.append(genre)
            video.genres = genres

        if data.category_ids is not None:
            categories = []
            for category_id in data.category_ids:
                category = await self.category_repo.get_by_id(db, category_id)
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Category {category_id} not found",
                    )
                categories.append(category)
            video.categories = categories

        return await self.video_repo.update(db, video)

    async def delete_video(self, db: AsyncSession, video_id: UUID) -> None:
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )
        await self.video_repo.delete(db, video)

    async def list_videos(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[Video], int]:
        return await self.video_repo.get_all_paginated(db, page, page_size)

    async def search_videos(
        self, db: AsyncSession, query: str = None, genre_id: UUID = None,
        category_id: UUID = None, page: int = 1, page_size: int = 20,
        semantic: bool = False,
    ) -> Tuple[List[Video], int]:
        if genre_id:
            return await self.video_repo.filter_by_genre(db, genre_id, page, page_size)
        if category_id:
            return await self.video_repo.filter_by_category(db, category_id, page, page_size)
        if query and semantic:
            return await self._search_semantic(db, query, page, page_size)
        if query:
            return await self.video_repo.search_by_title(db, query, page, page_size)
        return await self.video_repo.get_all_paginated(db, page, page_size)

    async def _search_semantic(
        self, db: AsyncSession, query: str, page: int, page_size: int
    ) -> Tuple[List[Video], int]:
        """Busca semantica via embedding — delega ao servico de IA para gerar o vetor."""
        from app.core.config import settings
        if not settings.SEMANTIC_SEARCH_ENABLED:
            return await self.video_repo.search_by_title(db, query, page, page_size)
        try:
            from app.integrations.ai_client import get_ai_client
            ai = get_ai_client()
            if ai is not None and ai.available:
                embedding = await ai.encode(query)
                if embedding:
                    return await self.video_repo.search_by_embedding(db, embedding, page, page_size)
        except Exception:
            pass
        # Fallback para busca classica se IA indisponivel
        return await self.video_repo.search_by_title(db, query, page, page_size)

    async def search_videos_semantic_scored(
        self,
        db: AsyncSession,
        query: str,
        *,
        limit: int,
        max_distance: float | None = None,
    ) -> List[Tuple[Video, float]]:
        """Busca semantica com score; usada pelo chat para filtrar relevancia."""
        from app.core.config import settings

        if not settings.SEMANTIC_SEARCH_ENABLED:
            videos, _total = await self.video_repo.search_by_title(db, query, 1, limit)
            return [(v, 0.0) for v in videos]

        try:
            from app.integrations.ai_client import get_ai_client

            ai = get_ai_client()
            if ai is not None and ai.available:
                embedding = await ai.encode(query)
                if embedding:
                    return await self.video_repo.search_by_embedding_scored(
                        db,
                        embedding,
                        limit=limit,
                        max_distance=max_distance,
                    )
        except Exception:
            pass
        videos, _total = await self.video_repo.search_by_title(db, query, 1, limit)
        return [(v, 0.0) for v in videos]

    async def search_videos_by_topic_keywords(
        self,
        db: AsyncSession,
        keywords: List[str],
        limit: int,
    ) -> List[Video]:
        return await self.video_repo.search_by_topic_keywords(db, keywords, limit)

    async def get_video_for_watch(self, db: AsyncSession, video_id: UUID) -> Video:
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )
        return video
