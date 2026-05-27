from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_role
from app.models.user import UserRole
from app.integrations.ai_client import get_ai_client

router = APIRouter()


@router.post("/index-embeddings", tags=["Admin"])
async def index_embeddings(
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    """Dispara indexação de embeddings no serviço de IA. Requer ADMIN."""
    ai = get_ai_client()
    if ai is None or not ai.available:
        raise HTTPException(status_code=503, detail="Serviço de IA indisponível.")

    result = await ai.index_embeddings()
    if result is None:
        raise HTTPException(status_code=503, detail="Serviço de IA indisponível.")

    return result
