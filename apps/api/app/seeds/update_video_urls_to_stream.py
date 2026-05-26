"""Atualiza as URLs dos 49 videos do dataset real para apontarem ao
endpoint local de streaming (/videos/{id}/stream).

Antes:  https://www.youtube.com/watch?v=...  (player Flutter nao toca)
Depois: /videos/{id}/stream                  (player Flutter toca direto)

Mantemos URL relativa — o app concatena com a base URL da API.
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.database.session import async_session_factory
from app.models.video import Video


async def update_urls() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(Video))
        videos = result.scalars().all()

        updated = 0
        skipped = 0
        for v in videos:
            # Apenas videos com UUID deterministico (do seed real) — content_id <= 1000
            if v.id.int > 1000:
                skipped += 1
                continue
            new_url = f"/videos/{v.id}/stream"
            if v.url == new_url:
                skipped += 1
                continue
            v.url = new_url
            updated += 1

        await session.commit()
        print(f"[update-urls] atualizados: {updated}  | pulados: {skipped}")
        print("[update-urls] novas URLs apontam para /videos/{id}/stream")


if __name__ == "__main__":
    asyncio.run(update_urls())
