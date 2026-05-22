import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.genre import GenreCreate, GenreUpdate, GenreResponse
from app.schemas.pagination import PaginatedResponse
from app.services.genre_service import GenreService

router = APIRouter()
genre_service = GenreService()


@router.post("", response_model=GenreResponse, status_code=201)
async def create_genre(
    data: GenreCreate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await genre_service.create_genre(db, data)


@router.get("", response_model=PaginatedResponse[GenreResponse])
async def list_genres(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    genres, total = await genre_service.list_genres(db, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=genres, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/{genre_id}", response_model=GenreResponse)
async def update_genre(
    genre_id: UUID,
    data: GenreUpdate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await genre_service.update_genre(db, genre_id, data)


@router.delete("/{genre_id}", status_code=204)
async def delete_genre(
    genre_id: UUID,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await genre_service.delete_genre(db, genre_id)
