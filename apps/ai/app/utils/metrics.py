"""Evaluation metrics for recommendation systems."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

RecommendFn = Callable[[int, list[tuple[int, float]], int], list[tuple[int, float]]]


def precision_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    """Proporção dos top-k que são relevantes."""
    if k <= 0:
        return 0.0
    top_k = recommended[:k]
    hits = len(set(top_k) & relevant)
    return hits / k


def recall_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    """Proporção dos relevantes que apareceram no top-k."""
    if not relevant or k <= 0:
        return 0.0
    top_k = recommended[:k]
    hits = len(set(top_k) & relevant)
    return hits / len(relevant)


def hit_rate_at_k(recommended: list[int], relevant: set[int], k: int) -> int:
    """1 se ao menos um item do top-k é relevante, 0 caso contrário."""
    if k <= 0:
        return 0
    top_k = recommended[:k]
    return 1 if set(top_k) & relevant else 0


def ndcg_at_k(
    recommended: list[int],
    relevant_with_ratings: dict[int, float],
    k: int,
) -> float:
    """NDCG@k usando os ratings_implicit como ganhos."""
    if k <= 0 or not relevant_with_ratings:
        return 0.0

    dcg = 0.0
    for index, item_id in enumerate(recommended[:k]):
        gain = relevant_with_ratings.get(item_id, 0.0)
        if gain > 0:
            dcg += gain / math.log2(index + 2)

    ideal_gains = sorted(relevant_with_ratings.values(), reverse=True)[:k]
    idcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal_gains))

    return dcg / idcg if idcg > 0 else 0.0


def map_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    """Mean Average Precision @ k."""
    if not relevant or k <= 0:
        return 0.0

    hits = 0
    precision_sum = 0.0
    for index, item_id in enumerate(recommended[:k]):
        if item_id in relevant:
            hits += 1
            precision_sum += hits / (index + 1)

    return precision_sum / min(len(relevant), k)


def _build_user_context(
    train_interactions: pd.DataFrame,
    test_interactions: pd.DataFrame,
) -> tuple[dict[int, list[tuple[int, float]]], dict[int, set[int]], dict[int, dict[int, float]]]:
    history: dict[int, list[tuple[int, float]]] = {}
    for row in train_interactions.itertuples(index=False):
        history.setdefault(int(row.user_id), []).append(
            (int(row.content_id), float(row.rating_implicit))
        )

    relevant_sets: dict[int, set[int]] = {}
    relevant_ratings: dict[int, dict[int, float]] = {}

    for row in test_interactions.itertuples(index=False):
        user_id = int(row.user_id)
        content_id = int(row.content_id)
        rating = float(row.rating_implicit)

        relevant_sets.setdefault(user_id, set()).add(content_id)
        ratings = relevant_ratings.setdefault(user_id, {})
        ratings[content_id] = max(ratings.get(content_id, 0.0), rating)

    return history, relevant_sets, relevant_ratings


def _resolve_recommend_fn(recommender: Any) -> RecommendFn:
    if callable(recommender):
        return recommender

    if hasattr(recommender, "recommend"):
        def _fn(user_id: int, history: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
            result = recommender.recommend(user_id=user_id, user_history=history, k=k)
            if isinstance(result, dict):
                return result.get("recommendations", [])
            return result

        return _fn

    raise TypeError("recommender must be callable or expose a recommend() method")


def evaluate_recommender(
    recommender: Any,
    test_interactions: pd.DataFrame,
    train_interactions: pd.DataFrame | None = None,
    k: int = 10,
) -> dict[str, float]:
    """Avalia um recommender nas interações de teste.

    Args:
        recommender: Função ``(user_id, history, k) -> [(content_id, score), ...]``
            ou objeto com método ``recommend(user_id=..., user_history=..., k=...)``.
        test_interactions: DataFrame com colunas ``user_id``, ``content_id``,
            ``rating_implicit`` (itens relevantes de teste por usuário).
        train_interactions: Histórico de treino para gerar recomendações. Se ``None``,
            usa histórico vazio (cold start).
        k: Cutoff das métricas.

    Returns:
        Dict com médias agregadas: ``precision@{k}``, ``recall@{k}``, ``hit_rate@{k}``,
        ``ndcg@{k}``, ``map@{k}``.
    """
    if train_interactions is None:
        train_interactions = pd.DataFrame(
            columns=["user_id", "content_id", "rating_implicit"],
        )

    recommend_fn = _resolve_recommend_fn(recommender)
    history_by_user, relevant_sets, relevant_ratings = _build_user_context(
        train_interactions,
        test_interactions,
    )

    metric_keys = {
        "precision": f"precision@{k}",
        "recall": f"recall@{k}",
        "hit_rate": f"hit_rate@{k}",
        "ndcg": f"ndcg@{k}",
        "map": f"map@{k}",
    }
    aggregates: dict[str, list[float]] = {key: [] for key in metric_keys.values()}

    for user_id, relevant in relevant_sets.items():
        if not relevant:
            continue

        history = history_by_user.get(user_id, [])
        try:
            recommendations = recommend_fn(user_id, history, k)
        except Exception:
            continue

        recommended_ids = [int(content_id) for content_id, _ in recommendations]
        ratings = relevant_ratings.get(user_id, {})

        aggregates[metric_keys["precision"]].append(
            precision_at_k(recommended_ids, relevant, k)
        )
        aggregates[metric_keys["recall"]].append(
            recall_at_k(recommended_ids, relevant, k)
        )
        aggregates[metric_keys["hit_rate"]].append(
            float(hit_rate_at_k(recommended_ids, relevant, k))
        )
        aggregates[metric_keys["ndcg"]].append(
            ndcg_at_k(recommended_ids, ratings, k)
        )
        aggregates[metric_keys["map"]].append(
            map_at_k(recommended_ids, relevant, k)
        )

    result: dict[str, float] = {}
    for metric_name, values in aggregates.items():
        result[metric_name] = float(np.mean(values)) if values else 0.0

    result["evaluated_users"] = float(len(aggregates[metric_keys["precision"]]))
    return result
