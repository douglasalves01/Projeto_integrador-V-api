from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.repositories.plan_repository import PlanRepository
from app.schemas.plan import PlanCreate, PlanUpdate


class PlanService:
    def __init__(self):
        self.plan_repo = PlanRepository()

    async def create_plan(self, db: AsyncSession, data: PlanCreate) -> Plan:
        existing = await self.plan_repo.get_by_name(db, data.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Plan with this name already exists",
            )
        plan = Plan(name=data.name, description=data.description, price=data.price)
        return await self.plan_repo.create(db, plan)

    async def get_plan(self, db: AsyncSession, plan_id: UUID) -> Plan:
        plan = await self.plan_repo.get_by_id(db, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found",
            )
        return plan

    async def list_plans(self, db: AsyncSession, page: int, page_size: int) -> Tuple[List[Plan], int]:
        return await self.plan_repo.get_all_paginated(db, page, page_size)

    async def update_plan(self, db: AsyncSession, plan_id: UUID, data: PlanUpdate) -> Plan:
        plan = await self.plan_repo.get_by_id(db, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found",
            )

        if data.name is not None:
            existing = await self.plan_repo.get_by_name(db, data.name)
            if existing and existing.id != plan_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Plan with this name already exists",
                )
            plan.name = data.name

        if data.description is not None:
            plan.description = data.description

        if data.price is not None:
            plan.price = data.price

        return await self.plan_repo.update(db, plan)

    async def delete_plan(self, db: AsyncSession, plan_id: UUID) -> None:
        plan = await self.plan_repo.get_by_id(db, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found",
            )

        in_use = await self.plan_repo.check_in_use(db, plan_id)
        if in_use:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Plan is in use and cannot be deleted",
            )

        await self.plan_repo.delete(db, plan)
