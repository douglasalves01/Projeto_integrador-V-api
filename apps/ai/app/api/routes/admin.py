"""Admin endpoints: hot-reload models and catalog."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import verify_admin_api_key
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services import catalog_loader, llm_recommendation_service as llmsvc

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_api_key)])

settings = get_settings()


class ReloadResponse(BaseModel):
    status: str
    detail: str | None = None
    info: dict | None = None
    item_count: int | None = None


class ModelVersionResponse(BaseModel):
    vodrec_version: str | None = None
    vodchat_version: str | None = None


def _read_version(path: str) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8").strip() or None


@router.post("/reload-models", response_model=ReloadResponse)
async def reload_models() -> ReloadResponse:
    """Reload VodRec and VodChat from disk without restarting the container."""
    with SessionLocal() as db:
        catalog = catalog_loader.load_catalog_from_db(db)
    result = llmsvc.reload_llm_models(catalog=catalog)
    return ReloadResponse(
        status=result["status"],
        detail=result.get("detail"),
        info=result.get("info"),
    )


@router.post("/reload-catalog", response_model=ReloadResponse)
async def reload_catalog() -> ReloadResponse:
    """Reload in-memory catalog from MySQL."""
    with SessionLocal() as db:
        catalog = catalog_loader.load_catalog_from_db(db)

    if not llmsvc.get_model_info().get("loaded"):
        return ReloadResponse(
            status="ok",
            detail="Catalog loaded in memory but LLM orchestrator is not active",
            item_count=len(catalog),
        )

    llmsvc.update_catalog(catalog)
    return ReloadResponse(status="ok", item_count=len(catalog))


@router.get("/model-version", response_model=ModelVersionResponse)
async def model_version() -> ModelVersionResponse:
    """Read VERSION.txt for VodRec and VodChat artifacts."""
    vodrec_base = Path(settings.VODREC_MODEL_PATH).parent
    vodchat_base = Path(settings.VODCHAT_ADAPTER_PATH).parent
    return ModelVersionResponse(
        vodrec_version=_read_version(str(vodrec_base / "VERSION.txt")),
        vodchat_version=_read_version(str(vodchat_base / "VERSION.txt")),
    )
