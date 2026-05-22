"""Collaborative filtering recommendations using implicit ALS."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from implicit.als import AlternatingLeastSquares
from implicit.nearest_neighbours import bm25_weight
from loguru import logger
from scipy.sparse import csr_matrix


class CollaborativeRecommender:
    """Implicit-feedback recommender trained with Alternating Least Squares (ALS)."""

    def __init__(
        self,
        factors: int = 64,
        regularization: float = 0.05,
        iterations: int = 20,
    ) -> None:
        self.model: AlternatingLeastSquares | None = None
        self.user_id_to_idx: dict[int, int] = {}
        self.idx_to_user_id: dict[int, int] = {}
        self.content_id_to_idx: dict[int, int] = {}
        self.idx_to_content_id: dict[int, int] = {}
        self.user_items_matrix: csr_matrix | None = None
        self.factors = factors
        self.regularization = regularization
        self.iterations = iterations

    def fit(
        self,
        user_items_matrix: csr_matrix,
        user_mapping: dict[int, int],
        content_mapping: dict[int, int],
    ) -> None:
        """Train ALS on implicit feedback with BM25 weighting.

        Args:
            user_items_matrix: CSR matrix shaped ``(n_users, n_items)`` with
                implicit ratings (e.g. completion or watch time).
            user_mapping: Maps external ``user_id`` to matrix row index.
            content_mapping: Maps external ``content_id`` to matrix column index.

        Raises:
            ValueError: If the matrix is empty or mappings are inconsistent.
            RuntimeError: If training fails.
        """
        if user_items_matrix.shape[0] == 0 or user_items_matrix.shape[1] == 0:
            raise ValueError("user_items_matrix must have at least one user and one item")

        matrix = user_items_matrix.tocsr()
        self.user_id_to_idx = {int(k): int(v) for k, v in user_mapping.items()}
        self.content_id_to_idx = {int(k): int(v) for k, v in content_mapping.items()}
        self.idx_to_user_id = {idx: uid for uid, idx in self.user_id_to_idx.items()}
        self.idx_to_content_id = {idx: cid for cid, idx in self.content_id_to_idx.items()}

        logger.info(
            "Training collaborative ALS model",
            factors=self.factors,
            regularization=self.regularization,
            iterations=self.iterations,
            n_users=matrix.shape[0],
            n_items=matrix.shape[1],
            n_interactions=int(matrix.nnz),
        )

        weighted = bm25_weight(matrix, K1=100, B=0.8).tocsr()
        self.user_items_matrix = weighted

        self.model = AlternatingLeastSquares(
            factors=self.factors,
            regularization=self.regularization,
            iterations=self.iterations,
        )

        started_at = time.perf_counter()
        self.model.fit(weighted)
        elapsed = time.perf_counter() - started_at

        logger.info(
            "Collaborative ALS training finished",
            factors=self.factors,
            regularization=self.regularization,
            iterations=self.iterations,
            training_seconds=round(elapsed, 3),
        )

    def recommend(
        self,
        user_id: int,
        k: int = 20,
        exclude_seen: bool = True,
    ) -> list[tuple[int, float]]:
        """Return top-``k`` collaborative recommendations for a user.

        Args:
            user_id: External user identifier.
            k: Number of recommendations to return.
            exclude_seen: When ``True``, omit items the user already interacted with.

        Returns:
            List of ``(content_id, score)`` sorted by descending score. Empty when
            the user is not in the training mapping (cold start).
        """
        if k <= 0:
            raise ValueError("k must be a positive integer")

        user_idx = self.user_id_to_idx.get(int(user_id))
        if user_idx is None:
            return []

        self._ensure_fitted()

        item_ids, scores = self.model.recommend(
            user_idx,
            self.user_items_matrix[user_idx],
            N=k,
            filter_already_liked_items=exclude_seen,
        )

        recommendations: list[tuple[int, float]] = []
        for idx, score in zip(item_ids, scores):
            if not np.isfinite(score):
                continue
            content_id = self.idx_to_content_id.get(int(idx))
            if content_id is None:
                continue
            recommendations.append((content_id, float(score)))

        return recommendations

    def score_all(self, user_id: int) -> np.ndarray | None:
        """Return min-max normalized scores for every item in the catalog.

        Scores are scaled to ``[0, 1]`` so they can be combined with content-based
        scores in a hybrid model.

        Args:
            user_id: External user identifier.

        Returns:
            1-D array of length ``n_items``, or ``None`` if the user is unknown.
        """
        user_idx = self.user_id_to_idx.get(int(user_id))
        if user_idx is None:
            return None

        self._ensure_fitted()
        raw_scores = self.model.user_factors[user_idx] @ self.model.item_factors.T
        return self._minmax_normalize(np.asarray(raw_scores, dtype=np.float64))

    def similar_items(self, content_id: int, k: int = 10) -> list[tuple[int, float]]:
        """Return items most similar to ``content_id`` using learned item factors.

        Args:
            content_id: External content identifier.
            k: Maximum number of similar items to return (excluding invalid entries).

        Returns:
            List of ``(content_id, score)`` sorted by descending similarity.
        """
        if k <= 0:
            raise ValueError("k must be a positive integer")

        item_idx = self.content_id_to_idx.get(int(content_id))
        if item_idx is None:
            return []

        self._ensure_fitted()

        item_ids, scores = self.model.similar_items(item_idx, N=k + 1)

        results: list[tuple[int, float]] = []
        for idx, score in zip(item_ids, scores):
            if int(idx) == item_idx:
                continue
            if not np.isfinite(score):
                continue
            mapped_id = self.idx_to_content_id.get(int(idx))
            if mapped_id is None:
                continue
            results.append((mapped_id, float(score)))
            if len(results) >= k:
                break

        return results

    def save(self, path: str) -> None:
        """Persist the trained model, mappings, and interaction matrix.

        Args:
            path: Destination file path (``.joblib`` recommended).
        """
        self._ensure_fitted()

        payload = {
            "model": self.model,
            "user_id_to_idx": self.user_id_to_idx,
            "idx_to_user_id": self.idx_to_user_id,
            "content_id_to_idx": self.content_id_to_idx,
            "idx_to_content_id": self.idx_to_content_id,
            "user_items_matrix": self.user_items_matrix,
            "factors": self.factors,
            "regularization": self.regularization,
            "iterations": self.iterations,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(payload, path)
        logger.info("Collaborative model saved", path=path)

    @classmethod
    def load(cls, path: str) -> CollaborativeRecommender:
        """Load a recommender previously saved with :meth:`save`.

        Args:
            path: File path written by :meth:`save`.

        Returns:
            Restored :class:`CollaborativeRecommender` instance.
        """
        payload: dict[str, Any] = joblib.load(path)
        instance = cls(
            factors=int(payload["factors"]),
            regularization=float(payload["regularization"]),
            iterations=int(payload["iterations"]),
        )
        instance.model = payload["model"]
        instance.user_id_to_idx = payload["user_id_to_idx"]
        instance.idx_to_user_id = payload["idx_to_user_id"]
        instance.content_id_to_idx = payload["content_id_to_idx"]
        instance.idx_to_content_id = payload["idx_to_content_id"]
        instance.user_items_matrix = payload["user_items_matrix"]
        return instance

    def _ensure_fitted(self) -> None:
        if self.model is None or self.user_items_matrix is None:
            raise RuntimeError("CollaborativeRecommender is not fitted. Call fit() first.")

    @staticmethod
    def _minmax_normalize(scores: np.ndarray) -> np.ndarray:
        """Scale scores to [0, 1], using 0.5 when all values are equal."""
        clean = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
        min_val = float(clean.min())
        max_val = float(clean.max())

        if max_val > min_val:
            return ((clean - min_val) / (max_val - min_val)).astype(np.float64)

        return np.full(clean.shape, 0.5, dtype=np.float64)
