"""Chatbot contextual via VodChat (apps/ai) com sugestões de vídeo do catálogo."""
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()
chat_service = ChatService()


@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    payload: ChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Envia mensagem ao VodChat e anexa vídeos relevantes via busca semântica."""
    user_id = UUID(current_user["user_id"])
    auth = request.headers.get("authorization", "")
    jwt = (
        auth.removeprefix("Bearer ").strip()
        if auth.lower().startswith("bearer ")
        else None
    )

    return await chat_service.handle(
        db=db,
        user_id=user_id,
        message=payload.message,
        jwt=jwt,
    )
