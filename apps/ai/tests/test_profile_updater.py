import pytest

from app.models.schemas_db import Content, Genre, UserProfileAI
from app.services.profile_updater import EMA_ALPHA, INACTIVE_DECAY, apply_profile_ema


def _content(genres: list[str]) -> Content:
    content = Content(
        id=1,
        title="Test",
        duration_sec=100,
    )
    content.genres = [Genre(id=i + 1, name=name) for i, name in enumerate(genres)]
    content.categories = []
    return content


def test_ema_updates_active_genre() -> None:
    profile = UserProfileAI(user_id=1, genre_weights={"Ação": 0.5}, category_weights={})
    content = _content(["Ação"])

    apply_profile_ema(profile, content, rating_implicit=1.0)

    expected = (1.0 - EMA_ALPHA) * 0.5 + EMA_ALPHA * 1.0
    assert profile.genre_weights["Ação"] == pytest.approx(expected)


def test_inactive_genres_decay() -> None:
    profile = UserProfileAI(
        user_id=1,
        genre_weights={"Ação": 0.8, "Comédia": 0.4},
        category_weights={},
    )
    content = _content(["Ação"])

    apply_profile_ema(profile, content, rating_implicit=1.0)

    assert profile.genre_weights["Comédia"] == pytest.approx(0.4 * INACTIVE_DECAY)
