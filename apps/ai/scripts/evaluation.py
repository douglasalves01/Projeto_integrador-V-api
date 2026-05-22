"""Offline evaluation helpers (data splits and recommend function factories)."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

import pandas as pd

from app.utils.metrics import evaluate_recommender as _evaluate_recommender
from app.utils.preprocessing import filter_users_min_interactions

RecommendFn = Callable[[int, list[tuple[int, float]], int], list[tuple[int, float]]]


def _split_train_test(
    interactions_df: pd.DataFrame,
    test_ratio: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []

    for _, group in interactions_df.groupby("user_id"):
        ordered = group.sort_values("started_at")
        n_test = max(1, int(len(ordered) * test_ratio))
        test_parts.append(ordered.tail(n_test))
        train_parts.append(ordered.iloc[: len(ordered) - n_test])

    return pd.concat(train_parts, ignore_index=True), pd.concat(test_parts, ignore_index=True)


def evaluate_recommender_legacy(
    name: str,
    recommend_fn: RecommendFn,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    k: int = 10,
) -> dict[str, Any]:
    """Backward-compatible wrapper around :func:`app.utils.metrics.evaluate_recommender`."""
    metrics = _evaluate_recommender(
        recommender=recommend_fn,
        test_interactions=test_df,
        train_interactions=train_df,
        k=k,
    )
    metrics["model"] = name
    return metrics


def evaluate_recommender(
    name: str,
    recommend_fn: RecommendFn,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    k: int = 10,
) -> dict[str, Any]:
    """Evaluate a recommender (legacy signature used by train_offline)."""
    return evaluate_recommender_legacy(name, recommend_fn, train_df, test_df, k=k)


def popularity_recommend(
    popularity: dict[int, float],
    all_content_ids: list[int],
) -> RecommendFn:
    ranked = sorted(all_content_ids, key=lambda cid: popularity.get(cid, 0.0), reverse=True)

    def _recommend(user_id: int, history: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
        del user_id
        seen = {content_id for content_id, _ in history}
        recs: list[tuple[int, float]] = []
        for content_id in ranked:
            if content_id in seen:
                continue
            recs.append((content_id, float(popularity.get(content_id, 0.0))))
            if len(recs) >= k:
                break
        return recs

    return _recommend


def random_recommend(
    all_content_ids: list[int],
    seed: int = 42,
) -> RecommendFn:
    rng = random.Random(seed)

    def _recommend(user_id: int, history: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
        del user_id
        seen = {content_id for content_id, _ in history}
        candidates = [cid for cid in all_content_ids if cid not in seen]
        rng.shuffle(candidates)
        return [(cid, rng.random()) for cid in candidates[:k]]

    return _recommend


def hybrid_recommend_fn(hybrid: Any) -> RecommendFn:
    def _recommend(user_id: int, history: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
        result = hybrid.recommend(user_id=user_id, user_history=history, k=k)
        return result["recommendations"]

    return _recommend


def content_based_recommend_fn(model: Any) -> RecommendFn:
    def _recommend(user_id: int, history: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
        del user_id
        return model.recommend(history, k=k, exclude_seen=True)

    return _recommend


def split_interactions(
    interactions_df: pd.DataFrame,
    test_ratio: float = 0.2,
    min_user_interactions: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split temporal por usuário (RFIA01 — apenas usuários com >=10 interações)."""
    eligible = filter_users_min_interactions(interactions_df, min_interactions=min_user_interactions)
    return _split_train_test(eligible, test_ratio=test_ratio)
