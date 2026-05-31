import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class UsageReport(BaseModel):
    total_users: int
    active_users: int
    total_watch_sessions: int
    average_watch_time_seconds: float


class RankedVideoReport(BaseModel):
    video_id: uuid.UUID
    title: str
    count: int


class AbandonmentVideoReport(BaseModel):
    video_id: uuid.UUID
    title: str
    abandonment_rate: float


class RankedGenreReport(BaseModel):
    genre_id: uuid.UUID
    name: str
    total_watch_time_seconds: int


class RankedUserReport(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    interaction_count: int


class UserEngagementReport(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    sessions: int
    total_watch_time_seconds: int
    average_watch_time_seconds: float
    average_percentage_watched: float


class InsightsReport(BaseModel):
    """Resumo executivo (gerado a partir das metricas reais, sem alucinacao)."""

    generated_at: datetime
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    headline: str
    highlights: List[str]
    usage: UsageReport
    average_percentage_watched: float
    completion_rate: float
    most_watched: List[RankedVideoReport]
    highest_abandonment: List[AbandonmentVideoReport]
    popular_genres: List[RankedGenreReport]
    top_users: List[UserEngagementReport]
