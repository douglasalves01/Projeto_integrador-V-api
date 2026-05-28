"""Endpoints de embeddings para busca semantica.

GET  /embeddings/encode    — gera embedding de uma query textual
POST /admin/index-embeddings — indexa todos os videos sem embedding no Postgres
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import verify_admin_api_key
from app.core.database import SessionLocal
from app.services.embedding_service import encode, get_embedding_stats, index_videos_in_db

router = APIRouter()


class EncodeResponse(BaseModel):
    embedding: list[float]
    dim: int


class IndexResponse(BaseModel):
    indexed: int
    status: str
    total_videos: int = 0
    total_with_embeddings: int = 0
    pending: int = 0


@router.get(
    "/embeddings/encode",
    response_model=EncodeResponse,
    tags=["embeddings"],
    summary="Gera embedding 384-dim para o texto fornecido.",
)
def encode_text(q: str = Query(..., min_length=1, max_length=2000)) -> EncodeResponse:
    emb = encode(q)
    return EncodeResponse(embedding=emb, dim=len(emb))


@router.post(
    "/admin/index-embeddings",
    response_model=IndexResponse,
    tags=["admin", "embeddings"],
    summary="Indexa videos sem embedding (requer pgvector instalado).",
    dependencies=[Depends(verify_admin_api_key)],
)
def index_embeddings() -> IndexResponse:
    with SessionLocal() as db:
        stats = get_embedding_stats(db)
        indexed = index_videos_in_db(db)
        if indexed == 0:
            stats = get_embedding_stats(db)
    return IndexResponse(
        indexed=indexed,
        status="ok",
        total_videos=stats["total_videos"],
        total_with_embeddings=stats["total_with_embeddings"],
        pending=stats["pending"],
    )
