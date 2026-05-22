"""Adapter SQLAlchemy para ler a tabela `watch_sessions` da API (Postgres + UUID).

A IA precisa apenas LER o historico de visualizacao. Como o monorepo usa um
unico Postgres e a API ja define todo o schema (alembic), aqui declaramos
apenas o subset minimo de campos que a IA consome.

Em hipotese alguma a IA deve fazer migrations — isso e responsabilidade da API.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class IABase(DeclarativeBase):
    """Base isolada — nao registra no metadata da API."""


class WatchSessionRO(IABase):
    """Read-only view da tabela watch_sessions da API."""
    __tablename__ = "watch_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    watch_time_seconds = Column(Integer, default=0, nullable=False)
    percentage_watched = Column(Float, default=0.0, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    abandoned = Column(Boolean, default=False, nullable=False)
