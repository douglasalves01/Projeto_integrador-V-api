"""Seed dos 49 videos reais do dataset brasileiro no Postgres.

Le `apps/ai/data/contents.parquet` (gerado por ingest_real_dataset.py) e
insere na tabela `videos` usando UUID DETERMINISTICO derivado do
`content_id` (UUID(int=content_id)), o que mantem o vocab do VodRec
sincronizado com os IDs no Postgres.

Execucao dentro do container:
    docker compose -f infra/docker-compose.yml exec api \\
        python -m app.seeds.seed_real_catalog

Ou local:
    cd apps/api && python -m app.seeds.seed_real_catalog
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.database.session import async_session_factory
from app.models.category import Category
from app.models.genre import Genre
from app.models.video import Video


# Pasta com o parquet (no container, montado em /app/ai_data; local, em apps/ai/data)
def _candidates() -> list[Path]:
    env = os.environ.get("REAL_CATALOG_PATH", "").strip()
    out: list[Path] = []
    if env:
        out.append(Path(env))
    out.extend([
        Path("/app/ai_data/contents.parquet"),
        Path("/app/models/contents.parquet"),
        Path(__file__).resolve().parents[3] / "ai" / "data" / "contents.parquet",
        Path("apps/ai/data/contents.parquet"),
    ])
    return out


def _find_parquet() -> Path:
    for p in _candidates():
        # precisa ser arquivo regular (.parquet), nao diretorio
        if p.is_file() and p.suffix == ".parquet":
            return p
    raise FileNotFoundError(
        "contents.parquet nao encontrado. Caminhos tentados:\n"
        + "\n".join(f"  - {p}" for p in _candidates())
    )


def _read_catalog(parquet_path: Path) -> list[dict]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas nao instalado no container. "
            "Suba via volume um JSON ou instale pandas no apps/api."
        ) from exc

    df = pd.read_parquet(parquet_path)
    return df.to_dict(orient="records")


async def seed_real() -> None:
    parquet_path = _find_parquet()
    print(f"[seed-real] lendo {parquet_path}")
    rows = _read_catalog(parquet_path)
    print(f"[seed-real] {len(rows)} videos no parquet")

    async with async_session_factory() as session:
        # Garante generos
        all_genre_names: set[str] = set()
        for r in rows:
            for g in list(r.get("genres") if r.get("genres") is not None else []):
                if g:
                    all_genre_names.add(str(g))

        existing = await session.execute(select(Genre))
        existing_by_name = {g.name: g for g in existing.scalars().all()}
        for name in sorted(all_genre_names):
            if name not in existing_by_name:
                genre = Genre(id=uuid.uuid4(), name=name)
                session.add(genre)
                existing_by_name[name] = genre
        await session.flush()

        # Garante categorias
        existing_cat = await session.execute(select(Category))
        existing_cat_by_name = {c.name: c for c in existing_cat.scalars().all()}
        all_cat_names: set[str] = set()
        for r in rows:
            for c in list(r.get("categories") if r.get("categories") is not None else []):
                if c:
                    all_cat_names.add(str(c))
        for name in sorted(all_cat_names):
            if name not in existing_cat_by_name:
                cat = Category(id=uuid.uuid4(), name=name)
                session.add(cat)
                existing_cat_by_name[name] = cat
        await session.flush()

        # Insere videos (UUID deterministico = UUID(int=content_id))
        inserted = 0
        skipped = 0
        for r in rows:
            content_id = int(r["content_id"])
            video_uuid = uuid.UUID(int=content_id)

            already = await session.get(Video, video_uuid)
            if already:
                skipped += 1
                continue

            video = Video(
                id=video_uuid,
                title=str(r.get("title", f"video_{content_id}"))[:200],
                description=(str(r.get("description") or ""))[:2000],
                url=str(r.get("external_url") or f"https://example/video/{content_id}")[:500],
                duration_seconds=int(r.get("duration_sec") or 0),
                release_date=date(int(r.get("release_year") or 2024), 1, 1),
                age_rating=None,
            )

            # vincular generos/categorias
            for g_name in list(r.get("genres") if r.get("genres") is not None else []):
                g = existing_by_name.get(str(g_name))
                if g:
                    video.genres.append(g)
            for c_name in list(r.get("categories") if r.get("categories") is not None else []):
                c = existing_cat_by_name.get(str(c_name))
                if c:
                    video.categories.append(c)

            session.add(video)
            inserted += 1

        await session.commit()
        print(f"[seed-real] inseridos: {inserted}  pulados (ja existiam): {skipped}")


if __name__ == "__main__":
    asyncio.run(seed_real())
