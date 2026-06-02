import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    plan_id: uuid.UUID


class UserProfileUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    plan_id: Optional[uuid.UUID] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
