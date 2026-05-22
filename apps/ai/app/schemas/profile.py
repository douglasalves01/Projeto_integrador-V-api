from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class UserProfileResponse(BaseModel):
    user_id: int
    genre_weights: dict[str, float] | None = None
    category_weights: dict[str, float] | None = None
    total_views: int
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)
