"""Contratos compartilhados entre API, IA e Analytics."""
from vod_shared.recommendations import (
    RecommendationItem,
    RecommendationsResponse,
    RecommendationStrategy,
)
from vod_shared.events import WatchEvent, InteractionEvent

__all__ = [
    "RecommendationItem",
    "RecommendationsResponse",
    "RecommendationStrategy",
    "WatchEvent",
    "InteractionEvent",
]
