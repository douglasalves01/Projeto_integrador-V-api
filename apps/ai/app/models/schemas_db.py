from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    view_histories: Mapped[list[ViewHistory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    profile_ai: Mapped[UserProfileAI | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    recommendation_events: Mapped[list[RecommendationEvent]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Content(Base):
    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    categories: Mapped[list[Category]] = relationship(
        secondary="content_categories",
        back_populates="contents",
    )
    genres: Mapped[list[Genre]] = relationship(
        secondary="content_genres",
        back_populates="contents",
    )
    content_categories: Mapped[list[ContentCategory]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
    )
    content_genres: Mapped[list[ContentGenre]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
    )
    view_histories: Mapped[list[ViewHistory]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
    )
    recommendation_events: Mapped[list[RecommendationEvent]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    contents: Mapped[list[Content]] = relationship(
        secondary="content_categories",
        back_populates="categories",
    )
    content_categories: Mapped[list[ContentCategory]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    contents: Mapped[list[Content]] = relationship(
        secondary="content_genres",
        back_populates="genres",
    )
    content_genres: Mapped[list[ContentGenre]] = relationship(
        back_populates="genre",
        cascade="all, delete-orphan",
    )


class ContentCategory(Base):
    __tablename__ = "content_categories"

    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    )

    content: Mapped[Content] = relationship(back_populates="content_categories")
    category: Mapped[Category] = relationship(back_populates="content_categories")


class ContentGenre(Base):
    __tablename__ = "content_genres"

    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
    )

    content: Mapped[Content] = relationship(back_populates="content_genres")
    genre: Mapped[Genre] = relationship(back_populates="content_genres")


class ViewHistory(Base):
    __tablename__ = "view_history"
    __table_args__ = (
        Index("ix_view_history_user_id", "user_id"),
        Index("ix_view_history_content_id", "content_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"),
        nullable=False,
    )
    watched_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    completion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="view_histories")
    content: Mapped[Content] = relationship(back_populates="view_histories")


class UserProfileAI(Base):
    __tablename__ = "user_profiles_ai"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    genre_weights: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    category_weights: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    total_views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="profile_ai")


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    shown_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    clicked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    played: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="recommendation_events")
    content: Mapped[Content] = relationship(back_populates="recommendation_events")
