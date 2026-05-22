import uuid
import enum
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class InteractionType(str, enum.Enum):
    CLICK = "CLICK"
    SEARCH = "SEARCH"
    WATCH = "WATCH"
    FAVORITE = "FAVORITE"
    UNFAVORITE = "UNFAVORITE"


class InteractionLog(Base):
    __tablename__ = "interaction_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=True)
    interaction_type = Column(Enum(InteractionType), nullable=False)
    search_query = Column(String(200), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="interaction_logs")
    video = relationship("Video", back_populates="interaction_logs")
