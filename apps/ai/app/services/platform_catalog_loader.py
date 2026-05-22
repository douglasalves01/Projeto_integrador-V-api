"""Load catalog metadata from the API Postgres schema (videos + genres)."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.platform_adapter import VideoRO
from app.services.content_id_mapper import get_mapper


def platform_schema_available(db: Session) -> bool:
    try:
        inspector = inspect(db.get_bind())
        tables = set(inspector.get_table_names())
        if "videos" in tables:
            return True
        tables.update(inspector.get_table_names(schema="public"))
        return "videos" in tables
    except Exception:
        return False


def load_catalog_from_platform_db(db: Session) -> dict[int, dict]:
    """Return ``{ content_id: {title, genres, duration_sec} }`` with stable int ids."""
    videos = db.query(VideoRO).all()
    video_ids = [video.id for video in videos]
    get_mapper().build(video_ids)

    catalog: dict[int, dict] = {}
    for video in videos:
        content_id = get_mapper().video_to_content(video.id)
        if content_id is None:
            continue
        catalog[content_id] = {
            "title": video.title,
            "genres": [genre.name for genre in video.genres],
            "duration_sec": int(video.duration_seconds),
        }
    return catalog
