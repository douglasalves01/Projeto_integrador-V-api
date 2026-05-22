import uuid
from datetime import datetime
from typing import Optional, Any, Dict

from pydantic import BaseModel, ConfigDict, Field


class InteractionLogCreate(BaseModel):
    user_id: uuid.UUID
    video_id: Optional[uuid.UUID] = None
    interaction_type: str
    search_query: Optional[str] = Field(None, max_length=200)
    metadata: Optional[Dict[str, Any]] = None


class InteractionLogResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    video_id: Optional[uuid.UUID] = None
    interaction_type: str
    search_query: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias="metadata_",
        serialization_alias="metadata",
    )
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
