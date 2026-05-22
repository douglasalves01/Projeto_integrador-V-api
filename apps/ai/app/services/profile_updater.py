"""EMA-based updates for user genre and category preference weights."""

from __future__ import annotations

from app.models.schemas_db import Content, UserProfileAI

EMA_ALPHA = 0.2
INACTIVE_DECAY = 0.99


def _update_weight_map(
    weights: dict[str, float],
    active_tags: set[str],
    rating_implicit: float,
    alpha: float = EMA_ALPHA,
    decay: float = INACTIVE_DECAY,
) -> dict[str, float]:
    updated = dict(weights)

    for tag in active_tags:
        old = float(updated.get(tag, 0.0))
        updated[tag] = (1.0 - alpha) * old + alpha * rating_implicit

    for tag in list(updated.keys()):
        if tag not in active_tags:
            updated[tag] = float(updated[tag]) * decay

    return updated


def apply_profile_ema(
    profile: UserProfileAI,
    content: Content,
    rating_implicit: float,
    alpha: float = EMA_ALPHA,
) -> None:
    """Update profile genre/category weights from a content interaction.

    Active genres and categories are updated with EMA. All other tags receive
    a light multiplicative decay so preferences evolve over time.
    """
    active_genres = {genre.name for genre in content.genres}
    active_categories = {category.name for category in content.categories}

    profile.genre_weights = _update_weight_map(
        profile.genre_weights or {},
        active_genres,
        rating_implicit,
        alpha=alpha,
    )
    profile.category_weights = _update_weight_map(
        profile.category_weights or {},
        active_categories,
        rating_implicit,
        alpha=alpha,
    )
