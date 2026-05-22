import uuid
from typing import Optional

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
