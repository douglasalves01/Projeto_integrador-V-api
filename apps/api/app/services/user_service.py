from typing import Tuple, List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.hashing import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class UserService:
    def __init__(self):
        self.user_repo = UserRepository()

    async def register(self, db: AsyncSession, user_data: UserCreate) -> User:
        # Check if email already exists
        existing = await self.user_repo.get_by_email(db, user_data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        # Validate plan exists
        from app.repositories.plan_repository import PlanRepository
        plan_repo = PlanRepository()
        plan = await plan_repo.get_by_id(db, user_data.plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Selected plan is invalid",
            )

        # Create user
        user = User(
            name=user_data.name,
            email=user_data.email,
            password_hash=hash_password(user_data.password),
            role=UserRole.USER,
            plan_id=user_data.plan_id,
            is_active=True,
        )
        return await self.user_repo.create(db, user)

    async def get_profile(self, db: AsyncSession, user_id: UUID) -> User:
        user = await self.user_repo.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def list_users(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[User], int]:
        return await self.user_repo.get_all_paginated(db, page, page_size)

    async def deactivate_user(
        self, db: AsyncSession, user_id: UUID, current_user_id: str
    ) -> User:
        if str(user_id) == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-deactivation is not allowed",
            )

        user = await self.user_repo.get_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user = await self.user_repo.deactivate(db, user_id)
        return user
