"""Constrói documentos textuais e ratings implícitos a partir do MySQL (ARQUITETURA §4)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.schemas_db import Content, ViewHistory
from app.utils.preprocessing import aggregate_interactions_df, build_text_doc

settings = get_settings()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def load_contents_df(db: Session | None = None) -> pd.DataFrame:
    """Catálogo para content-based: ``content_id``, ``text_doc``, ``genres``, ``categories``."""
    if db is None:
        with get_session() as session:
            return _load_contents(session)
    return _load_contents(db)


def _load_contents(db: Session) -> pd.DataFrame:
    contents = (
        db.query(Content)
        .options(
            joinedload(Content.genres),
            joinedload(Content.categories),
        )
        .all()
    )

    rows: list[dict] = []
    for content in contents:
        genre_names = [genre.name for genre in content.genres]
        category_names = [category.name for category in content.categories]
        rows.append(
            {
                "content_id": content.id,
                "title": content.title,
                "description": content.description or "",
                "text_doc": build_text_doc(
                    content.title,
                    content.description,
                    genre_names,
                    category_names,
                ),
                "genres": ",".join(genre_names),
                "categories": ",".join(category_names),
            }
        )

    return pd.DataFrame(rows)


def load_interactions_df(db: Session | None = None) -> pd.DataFrame:
    """Interações agregadas com ``rating_implicit`` (fórmula Seção 2.2)."""
    if db is None:
        with get_session() as session:
            return _load_interactions(session)
    return _load_interactions(db)


def _load_interactions(db: Session) -> pd.DataFrame:
    rows = (
        db.query(
            ViewHistory.user_id,
            ViewHistory.content_id,
            ViewHistory.completion,
            ViewHistory.started_at,
        )
        .order_by(ViewHistory.started_at.asc())
        .all()
    )

    raw = pd.DataFrame(
        [
            {
                "user_id": int(user_id),
                "content_id": int(content_id),
                "completion": float(completion),
                "started_at": started_at,
            }
            for user_id, content_id, completion, started_at in rows
        ]
    )
    if raw.empty:
        return raw
    return aggregate_interactions_df(raw)
