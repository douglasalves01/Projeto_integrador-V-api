"""Cache Redis para a API principal.

Estrategia de recomendacoes:
- Chave `api:recs:{user_id}` indica que as recomendacoes do usuario estao
  recentes no banco. Quando a chave existe, buscamos do DB sem recomputar.
- TTL configuravel via RECS_CACHE_TTL (default 300s / 5 min).
- Invalidada ao atualizar watch_session.
"""
from __future__ import annotations

import redis.asyncio as redis

from app.core.config import settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _recs_key(user_id: str) -> str:
    return f"api:recs:{user_id}"


async def is_recommendations_fresh(user_id: str) -> bool:
    """Retorna True se as recomendacoes do usuario ainda estao validas no cache."""
    try:
        client = _get_client()
        return bool(await client.exists(_recs_key(user_id)))
    except Exception:
        return False


async def mark_recommendations_fresh(user_id: str) -> None:
    """Marca as recomendacoes do usuario como recentes."""
    try:
        client = _get_client()
        await client.setex(_recs_key(user_id), settings.RECS_CACHE_TTL, "1")
    except Exception:
        pass


async def invalidate_recommendations(user_id: str) -> None:
    """Remove o flag de cache ao atualizar sessao de watch."""
    try:
        client = _get_client()
        await client.delete(_recs_key(user_id))
    except Exception:
        pass


async def ping_redis() -> bool:
    try:
        return bool(await _get_client().ping())
    except Exception:
        return False
