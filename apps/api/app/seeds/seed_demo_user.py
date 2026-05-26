"""Cria um usuario demo com historico de visualizacao coerente.

Objetivo: provar que o VodRec recomenda de verdade (nao so o fallback de
popularidade da API). O usuario gosta predominantemente de Culinaria e
Musica — depois disso o endpoint /recommendations deve sugerir conteudos
desses generos no topo.

Execucao:
    docker compose -f infra/docker-compose.yml exec api \\
        python -m app.seeds.seed_demo_user
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.hashing import hash_password
from app.database.session import async_session_factory
from app.models.user import User, UserRole
from app.models.video import Video
from app.models.watch_session import WatchSession


DEMO_EMAIL = "demo@streaming.com"
DEMO_PASSWORD = "demo1234"  # 8 chars para passar na validacao do App

# Categorias preferidas (matching com `genres` populados pelo seed_real_catalog).
FAVORITE_CATEGORIES = {"Culinaria", "Musica"}

# Quantos videos assistir das categorias favoritas
N_FAVORITE_VIEWS = 8
# E quantos "descobertas" aleatorias
N_OTHER_VIEWS = 2


async def seed_demo() -> None:
    async with async_session_factory() as session:
        # cria usuario se nao existir
        existing = await session.execute(
            select(User).where(User.email == DEMO_EMAIL)
        )
        user = existing.scalar_one_or_none()

        if user is None:
            user = User(
                id=uuid.uuid4(),
                name="Demo Viewer",
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                role=UserRole.USER,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            print(f"[demo] usuario criado: {user.email} ({user.id})")
        else:
            print(f"[demo] usuario ja existe: {user.email} ({user.id})")

        # Apaga historico anterior para nao duplicar
        prev = await session.execute(
            select(WatchSession).where(WatchSession.user_id == user.id)
        )
        for w in prev.scalars().all():
            await session.delete(w)
        await session.flush()

        # Pega todos videos com genero indicando categoria favorita (eager-load genres)
        all_videos = (
            await session.execute(select(Video).options(selectinload(Video.genres)))
        ).scalars().all()
        fav_videos: list[Video] = []
        other_videos: list[Video] = []
        for v in all_videos:
            genre_names = {g.name for g in v.genres}
            if genre_names & FAVORITE_CATEGORIES:
                fav_videos.append(v)
            else:
                other_videos.append(v)

        # Ordena por content_id (UUID(int=...)) para resultado deterministico
        fav_videos.sort(key=lambda v: v.id.int)
        other_videos.sort(key=lambda v: v.id.int)

        chosen_fav = fav_videos[:N_FAVORITE_VIEWS]
        chosen_other = other_videos[:N_OTHER_VIEWS]
        chosen = chosen_fav + chosen_other

        print(f"[demo] {len(chosen_fav)} favoritos + {len(chosen_other)} descobertas "
              f"= {len(chosen)} sessoes a criar")

        # Cria watch_sessions ao longo de 10 dias
        base = datetime.utcnow() - timedelta(days=10)
        for i, video in enumerate(chosen):
            in_favs = video in chosen_fav
            # favoritos -> completion alto; outros -> baixo
            completion = 0.95 if in_favs else 0.25
            watched = int(completion * (video.duration_seconds or 600))
            ws = WatchSession(
                id=uuid.uuid4(),
                user_id=user.id,
                video_id=video.id,
                started_at=base + timedelta(days=i, hours=20),
                watch_time_seconds=watched,
                percentage_watched=completion,
                completed=completion > 0.9,
                abandoned=completion < 0.3,
            )
            session.add(ws)

        await session.commit()
        print(f"[demo] historico criado para {user.email}")
        print(f"[demo] use:  email={DEMO_EMAIL}  password={DEMO_PASSWORD}")
        print(f"[demo] user_id (para /llm/...): {user.id}")


if __name__ == "__main__":
    asyncio.run(seed_demo())
