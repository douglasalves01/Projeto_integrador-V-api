import uuid
from datetime import datetime

from pydantic import BaseModel


class RecommendationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    video_id: uuid.UUID
    relevance_score: float
    explanation: str
    created_at: datetime

    class Config:
        from_attributes = True
