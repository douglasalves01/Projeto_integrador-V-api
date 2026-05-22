import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GenreCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class GenreUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)


class GenreResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
