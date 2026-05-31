import uuid
from datetime import datetime, date

from sqlalchemy import Column, String, Integer, DateTime, Date, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class Video(Base):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=True)
    summary = Column(Text, nullable=True)  # resumo gerado por IA (VodChat), backfill offline
    url = Column(String(500), nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    release_date = Column(Date, nullable=True)
    age_rating = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    genres = relationship("Genre", secondary="video_genres", back_populates="videos")
    categories = relationship("Category", secondary="video_categories", back_populates="videos")
    watch_sessions = relationship("WatchSession", back_populates="video")
    favorites = relationship("Favorite", back_populates="video")
    interaction_logs = relationship("InteractionLog", back_populates="video")
    recommendations = relationship("Recommendation", back_populates="video")
