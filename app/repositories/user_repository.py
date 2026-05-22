from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    async def create(self, db: AsyncSession, user: User) -> User:
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    async def get_by_id(self, db: AsyncSession, user_id: UUID) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_all_paginated(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[User], int]:
        # Count total
        count_result = await db.execute(select(func.count(User.id)))
        total = count_result.scalar()

        # Get page
        offset = (page - 1) * page_size
        result = await db.execute(
            select(User).offset(offset).limit(page_size).order_by(User.created_at.desc())
        )
        users = list(result.scalars().all())
        return users, total

    async def deactivate(self, db: AsyncSession, user_id: UUID) -> Optional[User]:
        user = await self.get_by_id(db, user_id)
        if user:
            user.is_active = False
            await db.flush()
            await db.refresh(user)
        return user
