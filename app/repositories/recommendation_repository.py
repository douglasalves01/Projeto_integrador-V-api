from typing import List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation import Recommendation


class RecommendationRepository:
    async def create(self, db: AsyncSession, recommendation: Recommendation) -> Recommendation:
        db.add(recommendation)
        await db.flush()
        await db.refresh(recommendation)
        return recommendation

    async def create_many(self, db: AsyncSession, recommendations: List[Recommendation]) -> List[Recommendation]:
        for rec in recommendations:
            db.add(rec)
        await db.flush()
        for rec in recommendations:
            await db.refresh(rec)
        return recommendations

    async def get_user_recommendations(
        self, db: AsyncSession, user_id: UUID
    ) -> List[Recommendation]:
        result = await db.execute(
            select(Recommendation)
            .where(Recommendation.user_id == user_id)
            .order_by(Recommendation.relevance_score.desc())
            .limit(10)
        )
        return list(result.scalars().all())

    async def get_all_paginated(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[Recommendation], int]:
        count_result = await db.execute(select(func.count(Recommendation.id)))
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(Recommendation)
            .offset(offset)
            .limit(page_size)
            .order_by(Recommendation.created_at.desc())
        )
        recs = list(result.scalars().all())
        return recs, total

    async def delete_user_recommendations(self, db: AsyncSession, user_id: UUID) -> None:
        result = await db.execute(
            select(Recommendation).where(Recommendation.user_id == user_id)
        )
        recs = result.scalars().all()
        for rec in recs:
            await db.delete(rec)
        await db.flush()
