"""Background execution of offline model training."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.services.model_loader import model_loader
from app.services.training_jobs import training_job_store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_SCRIPT = PROJECT_ROOT / "scripts" / "train_offline.py"


def run_offline_training(job_id: str) -> None:
    """Execute the offline training script and update job status."""
    training_job_store.update_job(job_id, status="running")

    try:
        result = subprocess.run(
            [sys.executable, str(TRAIN_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=3600,
        )

        if result.returncode != 0:
            training_job_store.update_job(
                job_id,
                status="failed",
                error=result.stderr.strip() or result.stdout.strip() or "Training failed",
            )
            logger.error("offline training failed", job_id=job_id, stderr=result.stderr)
            return

        reloaded = model_loader.reload_models()
        if not reloaded:
            training_job_store.update_job(
                job_id,
                status="failed",
                error=(
                    "Training finished but in-memory models could not be reloaded. "
                    "Check MODEL_PATH and artifact files under data/models."
                ),
            )
            logger.error("offline training reload failed", job_id=job_id)
            return

        training_job_store.update_job(
            job_id,
            status="completed",
            model_version=model_loader.current_model_version,
            metrics={"exit_code": result.returncode, "models_reloaded": reloaded},
            trained_at=datetime.now(timezone.utc),
            error=None,
        )
        logger.info(
            "offline training completed",
            job_id=job_id,
            model_version=model_loader.current_model_version,
            models_reloaded=reloaded,
        )
    except Exception as exc:
        training_job_store.update_job(job_id, status="failed", error=str(exc))
        logger.exception("offline training crashed", job_id=job_id)
