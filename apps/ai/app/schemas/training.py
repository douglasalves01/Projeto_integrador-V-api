from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TrainQueuedResponse(BaseModel):
    status: str
    job_id: str

    model_config = ConfigDict(from_attributes=True)


class TrainStatusResponse(BaseModel):
    job_id: str
    status: str
    model_version: str | None = None
    metrics: dict[str, Any] | None = None
    trained_at: datetime | None = None
    error: str | None = None

    model_config = ConfigDict(from_attributes=True)
