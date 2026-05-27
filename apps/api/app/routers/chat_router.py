"""Chatbot contextual via VodChat (apps/ai).

Repassa o JWT do usuario e a mensagem para o servico de IA.
Em caso de falha (IA indisponivel), retorna resposta de fallback em vez de
propagar o erro — mesma politica do recommendation_router.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    payload: ChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Envia mensagem para o VodChat e retorna a resposta.

    Requer autenticacao. O historico do usuario e injetado automaticamente
    pelo servico de IA a partir das watch_sessions.
    """
    user_id = UUID(current_user["user_id"])
    auth = request.headers.get("authorization", "")
    jwt = (
        auth.removeprefix("Bearer ").strip()
        if auth.lower().startswith("bearer ")
        else None
    )

    if jwt:
        try:
            from app.integrations.ai_client import get_ai_client
            ai = get_ai_client()
            if ai is not None and ai.available:
                reply = await ai.chat(user_id, jwt=jwt, message=payload.message)
                if reply:
                    return ChatResponse(reply=reply)
        except Exception:
            pass

    return ChatResponse(
        reply="Desculpe, o assistente esta temporariamente indisponivel. Tente novamente em instantes.",
        fallback=True,
    )
