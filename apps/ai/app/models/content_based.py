"""Content-based recommendation using TF-IDF and cosine similarity."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class ContentBasedRecommender:
    """Recommends content from TF-IDF text similarity and implicit feedback weights."""

    def __init__(self) -> None:
        self.tfidf_vectorizer: TfidfVectorizer | None = None
        self.tfidf_matrix: csr_matrix | None = None
        self.content_id_to_idx: dict[int, int] = {}
        self.idx_to_content_id: dict[int, int] = {}
        self.similarity_matrix: np.ndarray | None = None
        self._popularity_scores: np.ndarray | None = None

    def fit(self, contents_df: pd.DataFrame) -> None:
        """Train the TF-IDF vectorizer on ``contents_df['text_doc']``.

        Args:
            contents_df: DataFrame with at least ``content_id`` and ``text_doc``.
                Optional columns: ``popularity``, ``view_count`` (for empty-history
                fallback), ``genres`` (used by :meth:`explain`).

        Raises:
            ValueError: If required columns are missing or the frame is empty.
        """
        if contents_df.empty:
            raise ValueError("contents_df must not be empty")

        required = {"content_id", "text_doc"}
        missing = required - set(contents_df.columns)
        if missing:
            raise ValueError(f"contents_df is missing required columns: {sorted(missing)}")

        df = contents_df.drop_duplicates(subset=["content_id"]).reset_index(drop=True)

        self.content_id_to_idx = {
            int(row.content_id): idx for idx, row in df.iterrows()
        }
        self.idx_to_content_id = {idx: cid for cid, idx in self.content_id_to_idx.items()}

        texts = df["text_doc"].fillna("").astype(str).tolist()

        self.tfidf_vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=5000,
            min_df=2,
            stop_words=None,
        )
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
        self.similarity_matrix = None
        self._popularity_scores = self._build_popularity_scores(df)

    def score_for_user(self, user_history: list[tuple[int, float]]) -> np.ndarray:
        """Score all catalog items for a user profile derived from watch history.

        The user taste vector is a weighted average of TF-IDF vectors for consumed
        content, using ``rating_implicit`` as weight. Cosine similarity is computed
        against every item in the catalog.

        Args:
            user_history: List of ``(content_id, rating_implicit)`` pairs.

        Returns:
            1-D array of similarity scores with shape ``(n_contents,)``, aligned to
            internal matrix row indices (use :attr:`idx_to_content_id` to map back).

        Raises:
            RuntimeError: If :meth:`fit` has not been called yet.
        """
        self._ensure_fitted()

        n_contents = self.tfidf_matrix.shape[0]
        if not user_history:
            return self._popularity_scores.copy()

        weighted_sum: csr_matrix | None = None
        total_weight = 0.0

        for content_id, weight in user_history:
            if weight <= 0:
                continue
            idx = self.content_id_to_idx.get(int(content_id))
            if idx is None:
                continue
            row = self.tfidf_matrix[idx]
            weighted_sum = row.multiply(weight) if weighted_sum is None else weighted_sum + row.multiply(weight)
            total_weight += weight

        if weighted_sum is None or total_weight == 0.0:
            return self._popularity_scores.copy()

        user_profile = weighted_sum / total_weight
        scores = cosine_similarity(user_profile, self.tfidf_matrix).ravel()
        return np.asarray(scores, dtype=np.float64)

    def recommend(
        self,
        user_history: list[tuple[int, float]],
        k: int = 20,
        exclude_seen: bool = True,
    ) -> list[tuple[int, float]]:
        """Return top-``k`` recommendations as ``(content_id, score)`` pairs.

        Args:
            user_history: List of ``(content_id, rating_implicit)`` pairs.
            k: Maximum number of recommendations to return.
            exclude_seen: When ``True``, omit items already present in ``user_history``.

        Returns:
            List sorted by descending score.

        Raises:
            RuntimeError: If :meth:`fit` has not been called yet.
            ValueError: If ``k`` is not positive.
        """
        if k <= 0:
            raise ValueError("k must be a positive integer")

        scores = self.score_for_user(user_history)
        seen_ids: set[int] = set()
        if exclude_seen:
            seen_ids = {int(content_id) for content_id, _ in user_history}

        ranked_indices = np.argsort(scores)[::-1]
        recommendations: list[tuple[int, float]] = []

        for idx in ranked_indices:
            content_id = self.idx_to_content_id[int(idx)]
            if exclude_seen and content_id in seen_ids:
                continue
            recommendations.append((content_id, float(scores[idx])))
            if len(recommendations) >= k:
                break

        return recommendations

    def explain(
        self,
        content_id: int,
        user_history: list[tuple[int, float]],
        contents_df: pd.DataFrame,
    ) -> str:
        """Build a short natural-language explanation from the user's genre history.

        Args:
            content_id: Target content (reserved for future item-level explanations).
            user_history: List of ``(content_id, rating_implicit)`` pairs.
            contents_df: Catalog metadata; uses ``genres`` when available.

        Returns:
            Human-readable explanation string.
        """
        del content_id  # reserved for per-item explanations in a later iteration

        if not user_history:
            return "Recomendações baseadas em conteúdos populares"

        genre_counts: Counter[str] = Counter()
        for hist_content_id, weight in user_history:
            if weight <= 0:
                continue
            for genre in self._parse_genres(hist_content_id, contents_df):
                genre_counts[genre] += weight

        if not genre_counts:
            return "Recomendações baseadas no seu histórico de visualização"

        top_genres = [genre for genre, _ in genre_counts.most_common(3)]
        return self._format_genre_message(top_genres)

    def save(self, path: str) -> None:
        """Persist model artifacts to disk with joblib.

        Args:
            path: File path (``.joblib`` or ``.pkl`` recommended).

        Raises:
            RuntimeError: If :meth:`fit` has not been called yet.
        """
        self._ensure_fitted()

        payload = {
            "tfidf_vectorizer": self.tfidf_vectorizer,
            "tfidf_matrix": self.tfidf_matrix,
            "content_id_to_idx": self.content_id_to_idx,
            "idx_to_content_id": self.idx_to_content_id,
            "popularity_scores": self._popularity_scores,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(payload, path)

    @classmethod
    def load(cls, path: str) -> ContentBasedRecommender:
        """Load a fitted recommender from disk.

        Args:
            path: Path created by :meth:`save`.

        Returns:
            Fitted :class:`ContentBasedRecommender` instance.
        """
        payload: dict[str, Any] = joblib.load(path)
        instance = cls()
        instance.tfidf_vectorizer = payload["tfidf_vectorizer"]
        instance.tfidf_matrix = payload["tfidf_matrix"]
        instance.content_id_to_idx = payload["content_id_to_idx"]
        instance.idx_to_content_id = payload["idx_to_content_id"]
        instance._popularity_scores = payload["popularity_scores"]
        instance.similarity_matrix = None
        return instance

    def _ensure_fitted(self) -> None:
        if (
            self.tfidf_vectorizer is None
            or self.tfidf_matrix is None
            or self._popularity_scores is None
        ):
            raise RuntimeError("ContentBasedRecommender is not fitted. Call fit() first.")

    def _build_popularity_scores(self, df: pd.DataFrame) -> np.ndarray:
        """Build per-row popularity scores normalized to [0, 1]."""
        n = len(df)
        if "popularity" in df.columns:
            raw = df["popularity"].astype(float).to_numpy()
        elif "view_count" in df.columns:
            raw = df["view_count"].astype(float).to_numpy()
        else:
            raw = np.ones(n, dtype=np.float64)

        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
        if raw.max() > raw.min():
            normalized = (raw - raw.min()) / (raw.max() - raw.min())
        else:
            normalized = np.ones(n, dtype=np.float64)
        return normalized.astype(np.float64)

    @staticmethod
    def _parse_genres(content_id: int, contents_df: pd.DataFrame) -> list[str]:
        if "content_id" not in contents_df.columns or "genres" not in contents_df.columns:
            return []

        rows = contents_df.loc[contents_df["content_id"] == content_id, "genres"]
        if rows.empty:
            return []

        value = rows.iloc[0]
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return []

        if isinstance(value, (list, tuple, set)):
            return [str(g).strip() for g in value if str(g).strip()]

        text = str(value).strip()
        if not text:
            return []

        parts = [part.strip() for part in text.replace("|", ",").split(",")]
        return [part for part in parts if part]

    @staticmethod
    def _format_genre_message(genres: list[str]) -> str:
        if len(genres) == 1:
            return f"Você gosta de {genres[0]}"
        if len(genres) == 2:
            return f"Você gosta de {genres[0]} e {genres[1]}"
        return f"Você gosta de {genres[0]}, {genres[1]} e {genres[2]}"
