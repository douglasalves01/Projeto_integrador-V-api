"""Unit tests for recommendation scoring logic."""
import uuid
from unittest.mock import MagicMock

import pytest

from app.services.recommendation_service import (
    GENRE_AFFINITY_WEIGHT,
    CATEGORY_AFFINITY_WEIGHT,
    COMPLETION_RATE_WEIGHT,
    POPULARITY_WEIGHT,
    SEARCH_RELEVANCE_WEIGHT,
    RECENCY_WEIGHT,
    ABANDONMENT_PENALTY,
    RecommendationService,
)


class TestScoringWeights:
    """Verify scoring weights sum to 1.0."""

    def test_weights_sum_to_one(self):
        total = (
            GENRE_AFFINITY_WEIGHT
            + CATEGORY_AFFINITY_WEIGHT
            + COMPLETION_RATE_WEIGHT
            + POPULARITY_WEIGHT
            + SEARCH_RELEVANCE_WEIGHT
            + RECENCY_WEIGHT
        )
        assert total == pytest.approx(1.0)

    def test_abandonment_penalty_is_half(self):
        assert ABANDONMENT_PENALTY == 0.5


class TestScoreVideo:
    """Test the _score_video method in isolation."""

    def setup_method(self):
        self.service = RecommendationService()

    def _make_video(self, genre_ids=None, category_ids=None):
        video = MagicMock()
        video.id = uuid.uuid4()
        video.title = "Test Video"

        if genre_ids:
            genres = []
            for gid in genre_ids:
                g = MagicMock()
                g.id = gid
                g.name = f"Genre-{gid}"
                genres.append(g)
            video.genres = genres
        else:
            video.genres = []

        if category_ids:
            categories = []
            for cid in category_ids:
                c = MagicMock()
                c.id = cid
                c.name = f"Category-{cid}"
                categories.append(c)
            video.categories = categories
        else:
            video.categories = []

        return video

    def test_score_with_no_signals(self):
        video = self._make_video()
        score = self.service._score_video(
            video, {}, {}, {}, {}, {}, 0.0, {}
        )
        assert score == 0.0

    def test_score_with_genre_affinity(self):
        genre_id = uuid.uuid4()
        video = self._make_video(genre_ids=[genre_id])
        score = self.service._score_video(
            video,
            genre_scores={genre_id: 1.0},
            category_scores={},
            completion_rates={},
            popularity_scores={},
            search_scores={},
            recency_score=0.0,
            abandonment_rates={},
        )
        assert score == pytest.approx(GENRE_AFFINITY_WEIGHT)

    def test_score_with_category_affinity(self):
        cat_id = uuid.uuid4()
        video = self._make_video(category_ids=[cat_id])
        score = self.service._score_video(
            video,
            genre_scores={},
            category_scores={cat_id: 1.0},
            completion_rates={},
            popularity_scores={},
            search_scores={},
            recency_score=0.0,
            abandonment_rates={},
        )
        assert score == pytest.approx(CATEGORY_AFFINITY_WEIGHT)

    def test_score_with_popularity(self):
        video = self._make_video()
        score = self.service._score_video(
            video,
            genre_scores={},
            category_scores={},
            completion_rates={},
            popularity_scores={video.id: 1.0},
            search_scores={},
            recency_score=0.0,
            abandonment_rates={},
        )
        assert score == pytest.approx(POPULARITY_WEIGHT)

    def test_score_with_recency(self):
        video = self._make_video()
        score = self.service._score_video(
            video,
            genre_scores={},
            category_scores={},
            completion_rates={},
            popularity_scores={},
            search_scores={},
            recency_score=1.0,
            abandonment_rates={},
        )
        assert score == pytest.approx(RECENCY_WEIGHT)

    def test_abandonment_penalty_applied(self):
        genre_id = uuid.uuid4()
        video = self._make_video(genre_ids=[genre_id])

        # Score without penalty
        score_no_penalty = self.service._score_video(
            video,
            genre_scores={genre_id: 1.0},
            category_scores={},
            completion_rates={},
            popularity_scores={},
            search_scores={},
            recency_score=0.0,
            abandonment_rates={},
        )

        # Score with penalty (>50% abandonment)
        score_with_penalty = self.service._score_video(
            video,
            genre_scores={genre_id: 1.0},
            category_scores={},
            completion_rates={},
            popularity_scores={},
            search_scores={},
            recency_score=0.0,
            abandonment_rates={video.id: 0.6},
        )

        assert score_with_penalty == pytest.approx(score_no_penalty * ABANDONMENT_PENALTY)

    def test_abandonment_penalty_not_applied_below_threshold(self):
        genre_id = uuid.uuid4()
        video = self._make_video(genre_ids=[genre_id])

        score_no_penalty = self.service._score_video(
            video,
            genre_scores={genre_id: 1.0},
            category_scores={},
            completion_rates={},
            popularity_scores={},
            search_scores={},
            recency_score=0.0,
            abandonment_rates={},
        )

        # 50% abandonment (not > 50%)
        score_at_threshold = self.service._score_video(
            video,
            genre_scores={genre_id: 1.0},
            category_scores={},
            completion_rates={},
            popularity_scores={},
            search_scores={},
            recency_score=0.0,
            abandonment_rates={video.id: 0.5},
        )

        assert score_at_threshold == score_no_penalty

    def test_all_factors_combined(self):
        genre_id = uuid.uuid4()
        cat_id = uuid.uuid4()
        video = self._make_video(genre_ids=[genre_id], category_ids=[cat_id])

        score = self.service._score_video(
            video,
            genre_scores={genre_id: 1.0},
            category_scores={cat_id: 1.0},
            completion_rates={video.id: 1.0},
            popularity_scores={video.id: 1.0},
            search_scores={},
            recency_score=1.0,
            abandonment_rates={},
        )

        expected = (
            1.0 * GENRE_AFFINITY_WEIGHT
            + 1.0 * CATEGORY_AFFINITY_WEIGHT
            + 1.0 * COMPLETION_RATE_WEIGHT
            + 1.0 * POPULARITY_WEIGHT
            + 0.0 * SEARCH_RELEVANCE_WEIGHT
            + 1.0 * RECENCY_WEIGHT
        )
        assert score == pytest.approx(expected)


class TestGenerateExplanation:
    """Test explanation generation."""

    def setup_method(self):
        self.service = RecommendationService()

    def _make_video(self, genre_name="Action", category_name="Film"):
        video = MagicMock()
        video.id = uuid.uuid4()
        video.title = "Test Video"

        genre = MagicMock()
        genre.id = uuid.uuid4()
        genre.name = genre_name
        video.genres = [genre]

        category = MagicMock()
        category.id = uuid.uuid4()
        category.name = category_name
        video.categories = [category]

        return video, genre, category

    def test_explanation_with_genre_affinity(self):
        video, genre, _ = self._make_video()
        explanation = self.service._generate_explanation(
            video,
            genre_scores={genre.id: 0.5},
            category_scores={},
            popularity_scores={},
            search_scores={},
        )
        assert "genre affinity" in explanation.lower()

    def test_explanation_with_category_preference(self):
        video, _, category = self._make_video()
        explanation = self.service._generate_explanation(
            video,
            genre_scores={},
            category_scores={category.id: 0.5},
            popularity_scores={},
            search_scores={},
        )
        assert "category preference" in explanation.lower()

    def test_explanation_with_popularity(self):
        video, _, _ = self._make_video()
        explanation = self.service._generate_explanation(
            video,
            genre_scores={},
            category_scores={},
            popularity_scores={video.id: 0.8},
            search_scores={},
        )
        assert "popularity" in explanation.lower()

    def test_explanation_fallback_to_watch_history(self):
        video, _, _ = self._make_video()
        explanation = self.service._generate_explanation(
            video,
            genre_scores={},
            category_scores={},
            popularity_scores={},
            search_scores={},
        )
        assert "watch history" in explanation.lower()

    def test_explanation_is_never_empty(self):
        video, _, _ = self._make_video()
        explanation = self.service._generate_explanation(
            video, {}, {}, {}, {}
        )
        assert len(explanation) > 0
