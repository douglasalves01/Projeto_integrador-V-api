"""Tests for HybridRecommender switching strategies."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app.models.collaborative import CollaborativeRecommender
from app.models.content_based import ContentBasedRecommender
from app.models.hybrid import HybridRecommender


@pytest.fixture
def mock_cb() -> MagicMock:
    cb = MagicMock(spec=ContentBasedRecommender)
    cb.idx_to_content_id = {0: 1, 1: 2, 2: 3, 3: 4}
    cb.score_for_user.return_value = np.array([0.2, 0.9, 0.5, 0.1], dtype=np.float64)
    cb.explain.return_value = "Você gosta de Ação"
    return cb


@pytest.fixture
def mock_cf() -> MagicMock:
    cf = MagicMock(spec=CollaborativeRecommender)
    cf.idx_to_content_id = {0: 1, 1: 2, 2: 3, 3: 4}
    cf.score_all.return_value = np.array([0.8, 0.1, 0.6, 0.3], dtype=np.float64)
    return cf


@pytest.fixture
def hybrid(mock_cb: MagicMock, mock_cf: MagicMock) -> HybridRecommender:
    return HybridRecommender(mock_cb, mock_cf)


class TestHybridRecommender:
    def test_cold_start_uses_only_cb(self, hybrid: HybridRecommender, mock_cb: MagicMock, mock_cf: MagicMock) -> None:
        history = [(1, 1.0), (2, 0.5)]  # < 5 views

        result = hybrid.recommend(user_id=10, user_history=history, k=2)

        assert result["strategy"] == "cold_start"
        assert result["total_views"] == 2
        mock_cb.score_for_user.assert_called_once_with(history)
        mock_cf.score_all.assert_not_called()

    def test_transition_weights_06_04(self, hybrid: HybridRecommender, mock_cf: MagicMock) -> None:
        history = [(1, 1.0), (2, 1.0), (3, 1.0), (1, 0.8), (2, 0.6)]  # 5 views

        result = hybrid.recommend(user_id=10, user_history=history, k=3)

        assert result["strategy"] == "transition"
        mock_cf.score_all.assert_called_once_with(10)
        top_id, top_score = result["recommendations"][0]
        assert top_id == 4
        assert top_score == pytest.approx(0.6 * 0.0 + 0.4 * 0.3)

    def test_mature_weights_03_07(self, hybrid: HybridRecommender) -> None:
        history = [(1, 1.0), (2, 1.0), (3, 1.0)] + [(1, 0.5) for _ in range(17)]  # 20 views

        result = hybrid.recommend(user_id=10, user_history=history, k=2)

        assert result["strategy"] == "mature"
        top_id, top_score = result["recommendations"][0]
        assert top_id == 4
        assert top_score == pytest.approx(0.3 * 0.0 + 0.7 * 0.3)

    def test_always_excludes_seen_items(self, hybrid: HybridRecommender, mock_cb: MagicMock) -> None:
        mock_cb.score_for_user.return_value = np.array([0.9, 0.8, 0.7, 0.6])
        history = [(1, 1.0), (2, 1.0), (3, 1.0), (4, 1.0), (2, 0.5)]

        result = hybrid.recommend(user_id=10, user_history=history, k=10)
        content_ids = {cid for cid, _ in result["recommendations"]}

        assert not content_ids & {1, 2, 3, 4}

    def test_cf_none_fallback_to_cb(self, hybrid: HybridRecommender, mock_cf: MagicMock) -> None:
        mock_cf.score_all.return_value = None
        history = [(1, 1.0), (3, 1.0)] * 10

        result = hybrid.recommend(user_id=99, user_history=history, k=2)

        assert result["strategy"] == "mature"
        assert result["recommendations"][0][0] == 2

    def test_explain_delegates_to_cb(self, hybrid: HybridRecommender, mock_cb: MagicMock) -> None:
        contents_df = pd.DataFrame({"content_id": [1], "genres": ["Ação"]})
        message = hybrid.explain(4, [(1, 1.0)], contents_df)
        assert message == "Você gosta de Ação"

    def test_invalid_k_raises(self, hybrid: HybridRecommender) -> None:
        with pytest.raises(ValueError):
            hybrid.recommend(user_id=1, user_history=[], k=0)
