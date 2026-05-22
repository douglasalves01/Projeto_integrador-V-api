"""Feature preprocessing aligned with ARQUITETURA_IA (Seção 2.2 e 3.1)."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

# Interações com rating implícito >= limiar entram no ALS (Seção 2.2)
POSITIVE_INTERACTION_THRESHOLD = 0.4

GENRE_CATEGORY_TOKEN_WEIGHT = 3


def compute_implicit_rating(
    completion: float,
    *,
    revisited: bool = False,
    finished: bool | None = None,
) -> float:
    """Rating implícito: 0.6*completion + 0.3*revisited + 0.1*finished, clip [0, 1]."""
    if finished is None:
        finished = completion > 0.9

    raw = 0.6 * float(completion) + 0.3 * (1.0 if revisited else 0.0) + 0.1 * (1.0 if finished else 0.0)
    return max(0.0, min(1.0, raw))


def build_text_doc(
    title: str,
    description: str | None,
    genres: Iterable[str],
    categories: Iterable[str],
    *,
    token_weight: int = GENRE_CATEGORY_TOKEN_WEIGHT,
) -> str:
    """Documento textual com gêneros/categorias repetidos (peso ~3x via tokens)."""
    parts = [title.strip()]
    if description:
        parts.append(description.strip())

    for genre in genres:
        name = str(genre).strip()
        if name:
            parts.extend([name] * token_weight)

    for category in categories:
        name = str(category).strip()
        if name:
            parts.extend([name] * token_weight)

    return " ".join(parts)


def aggregate_interactions_df(interactions_df: pd.DataFrame) -> pd.DataFrame:
    """Agrega visualizações por (user_id, content_id) e calcula rating implícito."""
    if interactions_df.empty:
        return interactions_df.copy()

    grouped = interactions_df.groupby(["user_id", "content_id"], as_index=False)
    aggregated = grouped.agg(
        completion=("completion", "max"),
        view_count=("completion", "count"),
        started_at=("started_at", "max"),
    )
    aggregated["rating_implicit"] = aggregated.apply(
        lambda row: compute_implicit_rating(
            row["completion"],
            revisited=row["view_count"] > 1,
            finished=row["completion"] > 0.9,
        ),
        axis=1,
    )
    return aggregated


def filter_positive_interactions(
    interactions_df: pd.DataFrame,
    threshold: float = POSITIVE_INTERACTION_THRESHOLD,
) -> pd.DataFrame:
    """Mantém apenas interações positivas para treino ALS."""
    if "rating_implicit" not in interactions_df.columns:
        interactions_df = aggregate_interactions_df(interactions_df)
    return interactions_df[interactions_df["rating_implicit"] >= threshold].copy()


def filter_users_min_interactions(
    interactions_df: pd.DataFrame,
    min_interactions: int = 10,
) -> pd.DataFrame:
    """Filtra usuários com pelo menos ``min_interactions`` (protocolo RFIA01 — Seção 5.2)."""
    counts = interactions_df.groupby("user_id").size()
    valid_users = counts[counts >= min_interactions].index
    return interactions_df[interactions_df["user_id"].isin(valid_users)].copy()
