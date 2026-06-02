import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.pagination import PaginatedResponse
from app.schemas.user import UserProfileUpdate, UserResponse
from app.services.user_service import UserService

router = APIRouter()
user_service = UserService()


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_profile(db, UUID(current_user["user_id"]))
    return user


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.update_profile(
        db,
        UUID(current_user["user_id"]),
        payload,
    )
    return user


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    users, total = await user_service.list_users(db, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=users,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.deactivate_user(db, user_id, current_user["user_id"])
    return user
