"""Tests for recommendation evaluation metrics."""

import math

import pandas as pd
import pytest

from app.utils.metrics import (
    evaluate_recommender,
    hit_rate_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestMetricsAtK:
    def test_precision_at_k_manual(self) -> None:
        recommended = [10, 20, 30, 40, 50]
        relevant = {20, 40, 99}
        # hits at positions 2 and 4 -> 2/5
        assert precision_at_k(recommended, relevant, k=5) == pytest.approx(0.4)

    def test_recall_at_k_manual(self) -> None:
        recommended = [10, 20, 30, 40, 50]
        relevant = {20, 40, 99}
        # 2 of 3 relevant retrieved
        assert recall_at_k(recommended, relevant, k=5) == pytest.approx(2 / 3)

    def test_hit_rate_at_k_manual(self) -> None:
        assert hit_rate_at_k([1, 2, 3], {99}, k=3) == 0
        assert hit_rate_at_k([1, 2, 3], {2}, k=3) == 1

    def test_ndcg_at_k_manual(self) -> None:
        recommended = [100, 200, 300]
        relevant_ratings = {100: 3.0, 200: 2.0}

        dcg = 3.0 / math.log2(2) + 2.0 / math.log2(3)
        idcg = 3.0 / math.log2(2) + 2.0 / math.log2(3)

        assert ndcg_at_k(recommended, relevant_ratings, k=3) == pytest.approx(dcg / idcg)
        assert ndcg_at_k(recommended, relevant_ratings, k=3) == pytest.approx(1.0)

    def test_ndcg_zero_when_no_relevant_gains(self) -> None:
        assert ndcg_at_k([1, 2, 3], {}, k=3) == 0.0

    def test_evaluate_recommender_aggregates(self) -> None:
        train_df = pd.DataFrame(
            {
                "user_id": [1, 1, 2, 2],
                "content_id": [10, 11, 10, 12],
                "rating_implicit": [1.0, 0.8, 1.0, 0.5],
            }
        )
        test_df = pd.DataFrame(
            {
                "user_id": [1, 2],
                "content_id": [12, 12],
                "rating_implicit": [1.0, 1.0],
            }
        )

        popularity = {10: 3.0, 11: 2.0, 12: 5.0, 13: 1.0}
        ranked = sorted(popularity, key=popularity.get, reverse=True)

        def recommender(user_id: int, history: list[tuple[int, float]], k: int) -> list:
            del user_id
            seen = {cid for cid, _ in history}
            recs = []
            for cid in ranked:
                if cid in seen:
                    continue
                recs.append((cid, popularity[cid]))
                if len(recs) >= k:
                    break
            return recs

        metrics = evaluate_recommender(recommender, test_df, train_df, k=10)
        assert metrics["precision@10"] >= 0.0
        assert metrics["recall@10"] >= 0.0
        assert metrics["hit_rate@10"] >= 0.0
        assert metrics["ndcg@10"] >= 0.0
        assert metrics["map@10"] >= 0.0
        assert metrics["evaluated_users"] == 2.0
