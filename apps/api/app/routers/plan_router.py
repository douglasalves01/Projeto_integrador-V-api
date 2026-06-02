import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database.session import get_db
from app.models.user import UserRole
from app.schemas.plan import PlanCreate, PlanUpdate, PlanResponse
from app.schemas.pagination import PaginatedResponse
from app.services.plan_service import PlanService

router = APIRouter()
plan_service = PlanService()


@router.post("", response_model=PlanResponse, status_code=201)
async def create_plan(
    data: PlanCreate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await plan_service.create_plan(db, data)


@router.get("", response_model=PaginatedResponse[PlanResponse])
async def list_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
):
    """Lista planos sem autenticação (necessário para tela de cadastro)."""
    plans, total = await plan_service.list_plans(db, page, page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedResponse(
        items=plans, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: UUID,
    data: PlanUpdate,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await plan_service.update_plan(db, plan_id, data)


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: UUID,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await plan_service.delete_plan(db, plan_id)
