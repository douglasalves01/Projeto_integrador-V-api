import json
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def recs_cache_key(user_id: int | str, k: int) -> str:
    return f"recs:{user_id}:k{k}"


def recs_cache_pattern(user_id: int | str) -> str:
    return f"recs:{user_id}:*"


async def get_cached_recs(user_id: int | str, k: int) -> dict[str, Any] | None:
    """Return cached recommendation payload or None on miss."""
    client = await get_redis()
    raw = await client.get(recs_cache_key(user_id, k))
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached_recs(
    user_id: int | str,
    k: int,
    data: dict[str, Any],
    ttl: int | None = None,
) -> None:
    client = await get_redis()
    await client.setex(
        recs_cache_key(user_id, k),
        ttl or settings.RECS_CACHE_TTL,
        json.dumps(data, default=str),
    )


async def invalidate_user_recs_cache(user_id: int | str) -> int:
    """Delete all recommendation cache keys for a user. Returns keys removed."""
    client = await get_redis()
    deleted = 0
    async for key in client.scan_iter(match=recs_cache_pattern(user_id)):
        await client.delete(key)
        deleted += 1
    return deleted


async def ping_redis() -> bool:
    try:
        client = await get_redis()
        return bool(await client.ping())
    except Exception:
        return False
