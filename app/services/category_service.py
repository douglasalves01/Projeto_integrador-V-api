from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.repositories.category_repository import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self):
        self.category_repo = CategoryRepository()

    async def create_category(self, db: AsyncSession, data: CategoryCreate) -> Category:
        existing = await self.category_repo.get_by_name(db, data.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category with this name already exists",
            )
        category = Category(name=data.name)
        return await self.category_repo.create(db, category)

    async def get_category(self, db: AsyncSession, category_id: UUID) -> Category:
        category = await self.category_repo.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )
        return category

    async def list_categories(self, db: AsyncSession, page: int, page_size: int) -> Tuple[List[Category], int]:
        return await self.category_repo.get_all_paginated(db, page, page_size)

    async def update_category(self, db: AsyncSession, category_id: UUID, data: CategoryUpdate) -> Category:
        category = await self.category_repo.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        if data.name is not None:
            existing = await self.category_repo.get_by_name(db, data.name)
            if existing and existing.id != category_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Category with this name already exists",
                )
            category.name = data.name

        return await self.category_repo.update(db, category)

    async def delete_category(self, db: AsyncSession, category_id: UUID) -> None:
        category = await self.category_repo.get_by_id(db, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        in_use = await self.category_repo.check_in_use(db, category_id)
        if in_use:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category is in use and cannot be deleted",
            )

        await self.category_repo.delete(db, category)
