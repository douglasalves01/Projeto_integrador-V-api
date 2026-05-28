import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatVideoSuggestion(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    url: str
    duration_seconds: int

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    reply: str
    fallback: bool = False
    videos: List[ChatVideoSuggestion] = Field(default_factory=list)
    search_query: Optional[str] = None
    catalog_empty: bool = False
