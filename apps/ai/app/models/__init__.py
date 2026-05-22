"""ML model loaders, ORM entities, and inference wrappers."""

from app.models.collaborative import CollaborativeRecommender
from app.models.content_based import ContentBasedRecommender
from app.models.hybrid import HybridRecommender
from app.models.schemas_db import (
    Base,
    Category,
    Content,
    ContentCategory,
    ContentGenre,
    Genre,
    RecommendationEvent,
    User,
    UserProfileAI,
    ViewHistory,
)

__all__ = [
    "CollaborativeRecommender",
    "ContentBasedRecommender",
    "HybridRecommender",
    "Base",
    "Category",
    "Content",
    "ContentCategory",
    "ContentGenre",
    "Genre",
    "RecommendationEvent",
    "User",
    "UserProfileAI",
    "ViewHistory",
]
