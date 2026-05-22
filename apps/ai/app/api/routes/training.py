from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import verify_ai_api_key
from app.schemas.training import TrainQueuedResponse, TrainStatusResponse
from app.services.training_jobs import training_job_store
from app.services.training_runner import run_offline_training

router = APIRouter(prefix="/train", tags=["training"])


@router.post("", response_model=TrainQueuedResponse, dependencies=[Depends(verify_ai_api_key)])
async def queue_training(background_tasks: BackgroundTasks) -> TrainQueuedResponse:
    """Queue offline CF/CB model retraining (batch job)."""
    job_id = training_job_store.create_job()
    background_tasks.add_task(run_offline_training, job_id)
    return TrainQueuedResponse(status="queued", job_id=job_id)


@router.get("/status/{job_id}", response_model=TrainStatusResponse, dependencies=[Depends(verify_ai_api_key)])
async def get_training_status(job_id: str) -> TrainStatusResponse:
    job = training_job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return TrainStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        model_version=job.get("model_version"),
        metrics=job.get("metrics"),
        trained_at=job.get("trained_at"),
        error=job.get("error"),
    )
