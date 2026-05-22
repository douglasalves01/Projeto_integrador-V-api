"""Load catalog metadata for the LLM orchestrator (titles, genres)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.schemas_db import Content
from app.services.content_id_mapper import get_mapper
from app.services.platform_catalog_loader import (
    load_catalog_from_platform_db,
    platform_schema_available,
)


def _load_from_legacy_contents(db: Session) -> dict[int, dict]:
    contents = (
        db.query(Content)
        .options(
            joinedload(Content.genres),
            joinedload(Content.categories),
        )
        .all()
    )

    get_mapper().build_legacy_int_ids([int(content.id) for content in contents])

    catalog: dict[int, dict] = {}
    for content in contents:
        catalog[int(content.id)] = {
            "title": content.title,
            "genres": [genre.name for genre in content.genres],
            "duration_sec": int(content.duration_sec),
        }
    return catalog


def load_catalog_from_db(db: Session) -> dict[int, dict]:
    """Return ``{ content_id: {title, genres, duration_sec} }``."""
    if platform_schema_available(db):
        return load_catalog_from_platform_db(db)
    return _load_from_legacy_contents(db)
