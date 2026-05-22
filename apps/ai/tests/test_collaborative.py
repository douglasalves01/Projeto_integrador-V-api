"""Tests for CollaborativeRecommender (ALS + implicit)."""

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from app.models.collaborative import CollaborativeRecommender


def _build_matrix_10x20() -> tuple[csr_matrix, dict[int, int], dict[int, int]]:
    """10 users, 20 items sparse interaction matrix."""
    rows, cols, data = [], [], []
    user_mapping = {101 + i: i for i in range(10)}
    content_mapping = {201 + i: i for i in range(20)}

    for user_idx in range(10):
        for item_offset in range(4):
            item_idx = (user_idx * 2 + item_offset) % 20
            rows.append(user_idx)
            cols.append(item_idx)
            data.append(1.0 - item_offset * 0.1)

    matrix = csr_matrix((data, (rows, cols)), shape=(10, 20))
    return matrix, user_mapping, content_mapping


class TestCollaborativeRecommender:
    def test_fit_sparse_matrix(self) -> None:
        matrix, user_mapping, content_mapping = _build_matrix_10x20()
        model = CollaborativeRecommender(factors=8, regularization=0.05, iterations=5)
        model.fit(matrix, user_mapping, content_mapping)

        assert model.model is not None
        assert model.user_items_matrix.shape == (10, 20)

    def test_recommend_existing_user(self) -> None:
        matrix, user_mapping, content_mapping = _build_matrix_10x20()
        model = CollaborativeRecommender(factors=8, iterations=5)
        model.fit(matrix, user_mapping, content_mapping)

        recs = model.recommend(101, k=5, exclude_seen=True)
        assert len(recs) <= 5
        assert all(isinstance(cid, int) and isinstance(score, float) for cid, score in recs)

    def test_recommend_new_user_returns_empty(self) -> None:
        matrix, user_mapping, content_mapping = _build_matrix_10x20()
        model = CollaborativeRecommender(factors=8, iterations=5)
        model.fit(matrix, user_mapping, content_mapping)

        assert model.recommend(999, k=5) == []
        assert model.score_all(999) is None

    def test_score_all_shape_and_normalized(self) -> None:
        matrix, user_mapping, content_mapping = _build_matrix_10x20()
        model = CollaborativeRecommender(factors=8, iterations=5)
        model.fit(matrix, user_mapping, content_mapping)

        scores = model.score_all(101)
        assert scores is not None
        assert scores.shape == (20,)
        assert scores.min() >= 0.0
        assert scores.max() <= 1.0

    def test_save_and_load(self, tmp_path) -> None:
        matrix, user_mapping, content_mapping = _build_matrix_10x20()
        model = CollaborativeRecommender(factors=8, iterations=5)
        model.fit(matrix, user_mapping, content_mapping)

        path = tmp_path / "als_model.pkl"
        model.save(str(path))
        loaded = CollaborativeRecommender.load(str(path))

        assert loaded.user_id_to_idx == model.user_id_to_idx
        assert loaded.score_all(101) is not None

    def test_not_fitted_raises(self) -> None:
        model = CollaborativeRecommender()
        model.user_id_to_idx = {101: 0}
        with pytest.raises(RuntimeError):
            model.score_all(101)
