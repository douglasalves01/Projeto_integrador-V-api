import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price: Decimal = Field(..., ge=0, decimal_places=2)


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    price: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
