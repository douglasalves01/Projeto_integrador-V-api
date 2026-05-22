from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecommendationItem(BaseModel):
    content_id: int
    score: float
    reason: str


class RecommendationResponse(BaseModel):
    user_id: int
    model_version: str
    strategy: str
    total_views: int
    recommendations: list[RecommendationItem]
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InteractionUpdate(BaseModel):
    content_id: int
    watched_sec: int = Field(ge=0)
    total_sec: int = Field(gt=0)
    ended_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TrainResponse(BaseModel):
    status: str
    model_version: str
    metrics: dict[str, Any]
    trained_at: datetime

    model_config = ConfigDict(from_attributes=True)
