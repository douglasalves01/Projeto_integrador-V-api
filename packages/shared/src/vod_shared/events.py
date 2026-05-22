"""Eventos que trafegam entre API, IA e Analytics."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class WatchEvent(BaseModel):
    """Evento de visualizacao — publicado pela API ao final de uma sessao."""
    user_id: UUID
    content_id: UUID
    watched_seconds: int = Field(ge=0)
    total_seconds: int = Field(gt=0)
    completion: float = Field(ge=0.0, le=1.0)
    started_at: datetime
    ended_at: datetime


class InteractionType(str, Enum):
    PLAY = "play"
    PAUSE = "pause"
    LIKE = "like"
    DISLIKE = "dislike"
    SEARCH = "search"
    FAVORITE = "favorite"


class InteractionEvent(BaseModel):
    """Evento granular de interacao do usuario."""
    user_id: UUID
    content_id: UUID | None = None
    type: InteractionType
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime
