"""Read-only models for the shared Postgres schema owned by apps/api."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class PlatformBase(DeclarativeBase):
    pass


video_genres_ro = Table(
    "video_genres",
    PlatformBase.metadata,
    Column("video_id", UUID(as_uuid=True), ForeignKey("videos.id"), primary_key=True),
    Column("genre_id", UUID(as_uuid=True), ForeignKey("genres.id"), primary_key=True),
)


class GenreRO(PlatformBase):
    __tablename__ = "genres"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)


class VideoRO(PlatformBase):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=True)
    summary = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=False)
    release_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False)

    genres = relationship("GenreRO", secondary=video_genres_ro, lazy="joined")
