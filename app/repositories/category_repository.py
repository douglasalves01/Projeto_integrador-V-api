from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.video_category import video_category


class CategoryRepository:
    async def create(self, db: AsyncSession, category: Category) -> Category:
        db.add(category)
        await db.flush()
        await db.refresh(category)
        return category

    async def get_by_id(self, db: AsyncSession, category_id: UUID) -> Optional[Category]:
        result = await db.execute(select(Category).where(Category.id == category_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[Category]:
        result = await db.execute(select(Category).where(Category.name == name))
        return result.scalar_one_or_none()

    async def get_all(self, db: AsyncSession) -> List[Category]:
        result = await db.execute(select(Category).order_by(Category.name))
        return list(result.scalars().all())

    async def get_all_paginated(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[Category], int]:
        count_result = await db.execute(select(func.count(Category.id)))
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(Category).offset(offset).limit(page_size).order_by(Category.name)
        )
        categories = list(result.scalars().all())
        return categories, total

    async def update(self, db: AsyncSession, category: Category) -> Category:
        await db.flush()
        await db.refresh(category)
        return category

    async def delete(self, db: AsyncSession, category: Category) -> None:
        await db.delete(category)
        await db.flush()

    async def check_in_use(self, db: AsyncSession, category_id: UUID) -> bool:
        result = await db.execute(
            select(func.count()).select_from(video_category).where(
                video_category.c.category_id == category_id
            )
        )
        count = result.scalar()
        return count > 0
