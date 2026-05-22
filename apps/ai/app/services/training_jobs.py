"""In-memory training job registry for async offline training."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class TrainingJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "model_version": None,
            "metrics": None,
            "trained_at": None,
            "error": None,
            "created_at": datetime.now(timezone.utc),
        }
        return job_id

    def update_job(self, job_id: str, **fields: Any) -> None:
        if job_id in self._jobs:
            self._jobs[job_id].update(fields)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)


training_job_store = TrainingJobStore()
