from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.user import User


class PlanRepository:
    async def create(self, db: AsyncSession, plan: Plan) -> Plan:
        db.add(plan)
        await db.flush()
        await db.refresh(plan)
        return plan

    async def get_by_id(self, db: AsyncSession, plan_id: UUID) -> Optional[Plan]:
        result = await db.execute(select(Plan).where(Plan.id == plan_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[Plan]:
        result = await db.execute(select(Plan).where(Plan.name == name))
        return result.scalar_one_or_none()

    async def get_all(self, db: AsyncSession) -> List[Plan]:
        result = await db.execute(select(Plan).order_by(Plan.name))
        return list(result.scalars().all())

    async def get_all_paginated(
        self, db: AsyncSession, page: int, page_size: int
    ) -> Tuple[List[Plan], int]:
        count_result = await db.execute(select(func.count(Plan.id)))
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(Plan).offset(offset).limit(page_size).order_by(Plan.name)
        )
        plans = list(result.scalars().all())
        return plans, total

    async def update(self, db: AsyncSession, plan: Plan) -> Plan:
        await db.flush()
        await db.refresh(plan)
        return plan

    async def delete(self, db: AsyncSession, plan: Plan) -> None:
        await db.delete(plan)
        await db.flush()

    async def check_in_use(self, db: AsyncSession, plan_id: UUID) -> bool:
        result = await db.execute(
            select(func.count(User.id)).where(User.plan_id == plan_id)
        )
        count = result.scalar()
        return count > 0
