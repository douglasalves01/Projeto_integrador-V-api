import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.schemas.pagination import PaginatedResponse
from app.services.category_service import CategoryService

router = APIRouter()
category_service = CategoryService()


@router.post("", response_model=CategoryResponse, status_code=201)
async def create_category(
    data: CategoryCreate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await category_service.create_category(db, data)


@router.get("", response_model=PaginatedResponse[CategoryResponse])
async def list_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    categories, total = await category_service.list_categories(db, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=categories, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await category_service.update_category(db, category_id, data)


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: UUID,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await category_service.delete_category(db, category_id)
