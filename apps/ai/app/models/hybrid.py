"""Hybrid recommender combining content-based and collaborative filtering."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from app.models.collaborative import CollaborativeRecommender
from app.models.content_based import ContentBasedRecommender

Strategy = Literal["cold_start", "transition", "mature"]
ApiStrategy = Literal["content_based", "hybrid_weighted"]


def to_api_strategy(strategy: Strategy) -> ApiStrategy:
    """Mapeia estratégia interna para o campo da API (ARQUITETURA §6)."""
    if strategy == "cold_start":
        return "content_based"
    return "hybrid_weighted"


class HybridRecommender:
    """Switches and blends CB/CF models based on user interaction volume (RFIA03)."""

    def __init__(
        self,
        content_based: ContentBasedRecommender,
        collaborative: CollaborativeRecommender,
    ) -> None:
        self.cb = content_based
        self.cf = collaborative
        self.cold_start_threshold = 5
        self.transition_threshold = 20
        self.transition_weights = (0.6, 0.4)
        self.mature_weights = (0.3, 0.7)

    def recommend(
        self,
        user_id: int,
        user_history: list[tuple[int, float]],
        k: int = 20,
    ) -> dict[str, Strategy | int | list[tuple[int, float]]]:
        """Generate hybrid recommendations for a user.

        Args:
            user_id: External user identifier (collaborative model).
            user_history: List of ``(content_id, rating_implicit)`` pairs.
            k: Number of recommendations to return.

        Returns:
            Dictionary with ``strategy``, ``recommendations``, and ``total_views``.

        Raises:
            ValueError: If ``k`` is not positive.
            RuntimeError: If the content-based model is not fitted.
        """
        if k <= 0:
            raise ValueError("k must be a positive integer")

        total_views = len(user_history)
        strategy = self._resolve_strategy(total_views)
        seen_ids = {int(content_id) for content_id, _ in user_history}

        cb_scores = self._content_scores(user_history)
        cf_scores: dict[int, float] | None = None

        if strategy != "cold_start":
            cf_scores = self._collaborative_scores(user_id)

        cb_weight, cf_weight = self._resolve_weights(strategy, cf_scores is not None)
        if cf_scores is None:
            cf_scores = {}

        combined = self._blend_scores(cb_scores, cf_scores, cb_weight, cf_weight)
        recommendations = self._top_k(combined, seen_ids, k)

        return {
            "strategy": strategy,
            "recommendations": recommendations,
            "total_views": total_views,
        }

    def explain(
        self,
        content_id: int,
        user_history: list[tuple[int, float]],
        contents_df: pd.DataFrame,
    ) -> str:
        """Delegate explanation to the content-based model."""
        return self.cb.explain(content_id, user_history, contents_df)

    def _resolve_strategy(self, total_views: int) -> Strategy:
        if total_views < self.cold_start_threshold:
            return "cold_start"
        if total_views < self.transition_threshold:
            return "transition"
        return "mature"

    def _resolve_weights(
        self,
        strategy: Strategy,
        cf_available: bool,
    ) -> tuple[float, float]:
        if not cf_available or strategy == "cold_start":
            return 1.0, 0.0
        if strategy == "transition":
            return self.transition_weights
        return self.mature_weights

    def _content_scores(self, user_history: list[tuple[int, float]]) -> dict[int, float]:
        raw = self.cb.score_for_user(user_history)
        normalized = self._minmax_normalize(np.asarray(raw, dtype=np.float64))
        return {
            self.cb.idx_to_content_id[idx]: float(normalized[idx])
            for idx in range(normalized.shape[0])
        }

    def _collaborative_scores(self, user_id: int) -> dict[int, float] | None:
        scores = self.cf.score_all(user_id)
        if scores is None:
            return None
        return {
            self.cf.idx_to_content_id[idx]: float(scores[idx])
            for idx in range(scores.shape[0])
        }

    @staticmethod
    def _blend_scores(
        cb_scores: dict[int, float],
        cf_scores: dict[int, float],
        cb_weight: float,
        cf_weight: float,
    ) -> dict[int, float]:
        all_content_ids = set(cb_scores) | set(cf_scores)
        blended: dict[int, float] = {}

        for content_id in all_content_ids:
            blended[content_id] = (
                cb_weight * cb_scores.get(content_id, 0.0)
                + cf_weight * cf_scores.get(content_id, 0.0)
            )

        return blended

    @staticmethod
    def _top_k(
        scores: dict[int, float],
        seen_ids: set[int],
        k: int,
    ) -> list[tuple[int, float]]:
        candidates = [
            (content_id, score)
            for content_id, score in scores.items()
            if content_id not in seen_ids
        ]
        candidates.sort(key=lambda item: item[1], reverse=True)
        return candidates[:k]

    @staticmethod
    def _minmax_normalize(scores: np.ndarray) -> np.ndarray:
        clean = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
        min_val = float(clean.min())
        max_val = float(clean.max())

        if max_val > min_val:
            return ((clean - min_val) / (max_val - min_val)).astype(np.float64)

        return np.full(clean.shape, 0.5, dtype=np.float64)
