import uuid
from datetime import datetime, date
from typing import List, Optional

from pydantic import BaseModel, Field


AGE_RATINGS = ["L", "10", "12", "14", "16", "18"]


class VideoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    url: str = Field(..., min_length=1, max_length=500)
    duration_seconds: int = Field(..., ge=1, le=86400)
    genre_ids: List[uuid.UUID] = Field(..., min_length=1)
    category_ids: List[uuid.UUID] = Field(..., min_length=1)
    release_date: Optional[date] = None
    age_rating: Optional[str] = Field(None, pattern=r"^(L|10|12|14|16|18)$")


class VideoUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    url: Optional[str] = Field(None, min_length=1, max_length=500)
    duration_seconds: Optional[int] = Field(None, ge=1, le=86400)
    genre_ids: Optional[List[uuid.UUID]] = None
    category_ids: Optional[List[uuid.UUID]] = None
    release_date: Optional[date] = None
    age_rating: Optional[str] = Field(None, pattern=r"^(L|10|12|14|16|18)$")


class GenreInVideo(BaseModel):
    id: uuid.UUID
    name: str

    class Config:
        from_attributes = True


class CategoryInVideo(BaseModel):
    id: uuid.UUID
    name: str

    class Config:
        from_attributes = True


class VideoResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    url: str
    duration_seconds: int
    release_date: Optional[date] = None
    age_rating: Optional[str] = None
    genres: List[GenreInVideo] = []
    categories: List[CategoryInVideo] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
