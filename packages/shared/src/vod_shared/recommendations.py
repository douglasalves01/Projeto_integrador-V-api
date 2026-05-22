"""Schema de recomendacoes — contrato API <-> IA <-> Analytics."""
from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class RecommendationStrategy(str, Enum):
    EMPTY_HISTORY = "empty_history"
    COLD_START = "cold_start"
    VODREC = "vodrec"
    POPULARITY_FALLBACK = "popularity_fallback"
    PERSONALIZED_CLASSIC = "personalized_classic"


class RecommendationItem(BaseModel):
    content_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    title: str | None = None
    genres: list[str] = Field(default_factory=list)
    reason: str | None = None


class RecommendationsResponse(BaseModel):
    user_id: UUID
    model_version: str
    strategy: RecommendationStrategy
    total_views: int
    recommendations: list[RecommendationItem]
    top_explanation: str | None = None
