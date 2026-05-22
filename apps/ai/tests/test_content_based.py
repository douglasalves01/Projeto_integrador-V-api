"""Tests for ContentBasedRecommender."""

import numpy as np
import pandas as pd
import pytest

from app.models.content_based import ContentBasedRecommender


class TestContentBasedRecommender:
    def test_fit_small_dataset(self, catalog_df_5: pd.DataFrame) -> None:
        model = ContentBasedRecommender()
        model.fit(catalog_df_5)

        assert model.tfidf_matrix is not None
        assert model.tfidf_matrix.shape[0] == 5
        assert len(model.content_id_to_idx) == 5

    def test_score_for_user_returns_correct_shape(self, catalog_df_5: pd.DataFrame) -> None:
        model = ContentBasedRecommender()
        model.fit(catalog_df_5)

        scores = model.score_for_user([(1, 1.0), (2, 0.8)])
        assert scores.shape == (5,)
        assert np.isfinite(scores).all()
        assert scores.min() >= 0.0 or scores.max() <= 1.0  # cosine or popularity

    def test_recommend_exclude_seen(self, catalog_df_5: pd.DataFrame) -> None:
        model = ContentBasedRecommender()
        model.fit(catalog_df_5)

        history = [(1, 1.0), (2, 0.8)]
        recs = model.recommend(history, k=3, exclude_seen=True)

        recommended_ids = {cid for cid, _ in recs}
        assert 1 not in recommended_ids
        assert 2 not in recommended_ids
        assert len(recs) == 3
        assert recs[0][1] >= recs[-1][1]

    def test_save_load_preserves_results(self, catalog_df_5: pd.DataFrame, tmp_path) -> None:
        model = ContentBasedRecommender()
        model.fit(catalog_df_5)

        original_recs = model.recommend([(1, 1.0)], k=3, exclude_seen=True)

        path = tmp_path / "content_based.pkl"
        model.save(str(path))
        loaded = ContentBasedRecommender.load(str(path))

        loaded_recs = loaded.recommend([(1, 1.0)], k=3, exclude_seen=True)
        assert loaded.content_id_to_idx == model.content_id_to_idx
        assert [cid for cid, _ in loaded_recs] == [cid for cid, _ in original_recs]

    def test_empty_history_uses_popularity(self, catalog_df_5: pd.DataFrame) -> None:
        model = ContentBasedRecommender()
        model.fit(catalog_df_5)

        recs = model.recommend([], k=1, exclude_seen=False)
        assert recs[0][0] == 4  # highest popularity in fixture

    def test_not_fitted_raises(self) -> None:
        model = ContentBasedRecommender()
        with pytest.raises(RuntimeError):
            model.recommend([(1, 1.0)])
