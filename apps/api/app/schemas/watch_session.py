import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WatchSessionUpdate(BaseModel):
    watch_time_seconds: int = Field(..., ge=0)


class WatchSessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    video_id: uuid.UUID
    started_at: datetime
    watch_time_seconds: int
    percentage_watched: float
    completed: bool
    abandoned: bool
    updated_at: datetime

    class Config:
        from_attributes = True
