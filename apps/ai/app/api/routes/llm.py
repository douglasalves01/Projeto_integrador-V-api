"""REST endpoints do VodRec-Transformer e VodChat.

Le `watch_sessions` do Postgres compartilhado (mesmo schema da API). user_id e
content_id sao UUIDs — mapeados internamente para os tokens inteiros do
modelo via `vocab.json`.
"""

from __future__ import annotations

import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ensure_user_access, get_current_user
from app.models.db_adapter import WatchSessionRO
from app.services import llm_recommendation_service as svc
from app.services.content_id_mapper import get_mapper

router = APIRouter(prefix="/llm", tags=["llm"])


class RecommendationItem(BaseModel):
    content_id: UUID
    score: float
    title: str | None = None
    genres: list[str] = Field(default_factory=list)
    reason: str | None = None


class RecommendationsResponse(BaseModel):
    user_id: UUID
    model_version: str
    strategy: str
    total_views: int
    recommendations: list[RecommendationItem]
    top_explanation: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str


class ModelInfoResponse(BaseModel):
    loaded: bool
    vodrec: dict | None = None
    vodchat: dict | None = None


def _load_user_history(db: Session, user_id: UUID) -> list[UUID]:
    """Retorna lista de video_ids (UUID) ordenada por started_at."""
    stmt = (
        select(WatchSessionRO.video_id)
        .where(WatchSessionRO.user_id == user_id)
        .order_by(WatchSessionRO.started_at.asc())
    )
    return [row[0] for row in db.execute(stmt).all()]


def _to_recommendation_items(result: dict) -> list[RecommendationItem]:
    mapper = get_mapper()
    items: list[RecommendationItem] = []
    for raw in result.get("recommendations", []):
        video_id = mapper.content_to_video(int(raw["content_id"]))
        if video_id is None:
            continue
        items.append(
            RecommendationItem(
                content_id=video_id,
                score=float(raw.get("score", 0.0)),
                title=raw.get("title"),
                genres=raw.get("genres") or [],
                reason=raw.get("reason"),
            )
        )
    return items


@router.get(
    "/recommendations/{user_id}",
    response_model=RecommendationsResponse,
    summary="Recomendacoes do VodRec-Transformer (explicacao opcional via VodChat).",
)
def get_recommendations(
    user_id: UUID,
    k: Annotated[int, Query(ge=1, le=100)] = 20,
    with_explanation: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> RecommendationsResponse:
    ensure_user_access(current_user, user_id)

    if not svc.get_model_info().get("loaded"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM models are not loaded",
        )

    history = get_mapper().videos_to_contents(_load_user_history(db, user_id))

    try:
        result = svc.get_recommendations(
            history_content_ids=history,
            k=k,
            with_explanation=with_explanation,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return RecommendationsResponse(
        user_id=user_id,
        model_version=result.get("model_version", "unknown"),
        strategy=result.get("strategy", "unknown"),
        total_views=result.get("total_views", len(history)),
        recommendations=_to_recommendation_items(result),
        top_explanation=result.get("top_explanation"),
    )


@router.post(
    "/chat/{user_id}",
    response_model=ChatResponse,
    summary="Conversa livre com o VodChat.",
)
def chat(
    user_id: UUID,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ChatResponse:
    started = time.perf_counter()
    logger.info("LLM chat request started", user_id=str(user_id), chars=len(payload.message))
    ensure_user_access(current_user, user_id)

    if not svc.get_model_info().get("loaded"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM models are not loaded",
        )

    history = get_mapper().videos_to_contents(_load_user_history(db, user_id))

    try:
        result = svc.chat_message(
            user_message=payload.message,
            history_content_ids=history,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    logger.info(
        "LLM chat request completed",
        user_id=str(user_id),
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        reply_chars=len(result.get("reply") or ""),
    )
    return ChatResponse(**result)


@router.get(
    "/info",
    response_model=ModelInfoResponse,
    summary="Metadados dos modelos LLM carregados.",
)
def info() -> ModelInfoResponse:
    return ModelInfoResponse(**svc.get_model_info())
