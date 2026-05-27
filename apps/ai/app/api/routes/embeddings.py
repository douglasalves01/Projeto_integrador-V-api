"""Endpoints de embeddings para busca semantica.

GET  /embeddings/encode    — gera embedding de uma query textual
POST /admin/index-embeddings — indexa todos os videos sem embedding no Postgres
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import verify_admin_api_key
from app.core.database import SessionLocal
from app.services.embedding_service import encode, index_videos_in_db

router = APIRouter()


class EncodeResponse(BaseModel):
    embedding: list[float]
    dim: int


class IndexResponse(BaseModel):
    indexed: int
    status: str


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
        indexed = index_videos_in_db(db)
    return IndexResponse(indexed=indexed, status="ok")
