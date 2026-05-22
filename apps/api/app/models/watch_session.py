import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class WatchSession(Base):
    __tablename__ = "watch_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    watch_time_seconds = Column(Integer, default=0, nullable=False)
    percentage_watched = Column(Float, default=0.0, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    abandoned = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="watch_sessions")
    video = relationship("Video", back_populates="watch_sessions")
