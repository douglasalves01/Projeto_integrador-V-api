#!/usr/bin/env python3
"""Offline training pipeline for VOD recommendation models."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger
from scipy.sparse import csr_matrix

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import setup_logging  # noqa: E402
from app.models.collaborative import CollaborativeRecommender  # noqa: E402
from app.models.content_based import ContentBasedRecommender  # noqa: E402
from app.models.hybrid import HybridRecommender  # noqa: E402
from scripts.evaluation import (  # noqa: E402
    content_based_recommend_fn,
    evaluate_recommender,
    hybrid_recommend_fn,
    popularity_recommend,
    random_recommend,
    split_interactions,
)
from app.utils.preprocessing import filter_positive_interactions  # noqa: E402
from app.models.schemas_db import UserProfileAI  # noqa: E402
from scripts.feature_extractor import get_session, load_contents_df, load_interactions_df  # noqa: E402

MODELS_DIR = PROJECT_ROOT / "data" / "models"
CB_MODEL_PATH = MODELS_DIR / "content_based.pkl"
ALS_MODEL_PATH = MODELS_DIR / "als_model.pkl"
METRICS_PATH = MODELS_DIR / "metrics.json"
VERSION_PATH = MODELS_DIR / "VERSION.txt"

MIN_USER_INTERACTIONS = 3
MIN_CONTENT_INTERACTIONS = 2
VERSION_PATTERN = re.compile(r"^hybrid-v(\d+)\.(\d+)\.(\d+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train VOD recommendation models offline")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Train content-based and collaborative models (default)",
    )
    parser.add_argument(
        "--cb-only",
        action="store_true",
        help="Train only the content-based model",
    )
    return parser.parse_args()


def filter_interactions(interactions_df: pd.DataFrame) -> pd.DataFrame:
    user_counts = interactions_df.groupby("user_id").size()
    content_counts = interactions_df.groupby("content_id").size()

    valid_users = user_counts[user_counts >= MIN_USER_INTERACTIONS].index
    valid_contents = content_counts[content_counts >= MIN_CONTENT_INTERACTIONS].index

    filtered = interactions_df[
        interactions_df["user_id"].isin(valid_users)
        & interactions_df["content_id"].isin(valid_contents)
    ].copy()

    logger.info(
        "Interactions filtered",
        raw=len(interactions_df),
        filtered=len(filtered),
        users=int(filtered["user_id"].nunique()),
        contents=int(filtered["content_id"].nunique()),
    )
    return filtered


def enrich_contents_with_popularity(
    contents_df: pd.DataFrame,
    interactions_df: pd.DataFrame,
) -> pd.DataFrame:
    popularity = (
        interactions_df.groupby("content_id")
        .size()
        .reset_index(name="view_count")
    )
    enriched = contents_df.merge(popularity, on="content_id", how="left")
    enriched["view_count"] = enriched["view_count"].fillna(0).astype(float)
    return enriched


def sync_cf_embeddings(db, cf_model: CollaborativeRecommender) -> None:
    """Persiste fatores latentes do ALS em ``user_profiles_ai.embedding``."""
    if cf_model.model is None:
        return

    for user_id, user_idx in cf_model.user_id_to_idx.items():
        embedding = cf_model.model.user_factors[user_idx].tolist()
        profile = db.query(UserProfileAI).filter(UserProfileAI.user_id == user_id).first()
        if profile is None:
            profile = UserProfileAI(
                user_id=user_id,
                genre_weights={},
                category_weights={},
                total_views=0,
                last_updated=datetime.now(timezone.utc),
            )
            db.add(profile)
        profile.embedding = embedding
    db.commit()
    logger.info("CF user embeddings synced to user_profiles_ai", users=len(cf_model.user_id_to_idx))


def build_user_item_matrix(
    interactions_df: pd.DataFrame,
) -> tuple[csr_matrix, dict[int, int], dict[int, int]]:
    user_ids = sorted(interactions_df["user_id"].unique().astype(int).tolist())
    content_ids = sorted(interactions_df["content_id"].unique().astype(int).tolist())

    user_mapping = {user_id: index for index, user_id in enumerate(user_ids)}
    content_mapping = {content_id: index for index, content_id in enumerate(content_ids)}

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []

    for row in interactions_df.itertuples(index=False):
        rows.append(user_mapping[int(row.user_id)])
        cols.append(content_mapping[int(row.content_id)])
        data.append(float(row.rating_implicit))

    matrix = csr_matrix(
        (data, (rows, cols)),
        shape=(len(user_ids), len(content_ids)),
    )
    return matrix, user_mapping, content_mapping


def bump_version(current: str | None) -> str:
    if current:
        match = VERSION_PATTERN.match(current.strip())
        if match:
            major, minor, patch = map(int, match.groups())
            return f"hybrid-v{major}.{minor}.{patch + 1}"
    return "hybrid-v1.0.0"


def read_current_version() -> str | None:
    if not VERSION_PATH.exists():
        return None
    return VERSION_PATH.read_text(encoding="utf-8").strip() or None


def run_evaluation(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    contents_df: pd.DataFrame,
    cb_model: ContentBasedRecommender,
    cf_model: CollaborativeRecommender | None,
    full_training: bool,
) -> dict:
    all_content_ids = contents_df["content_id"].astype(int).tolist()
    popularity = (
        train_df.groupby("content_id").size().astype(float).to_dict()
    )

    metrics: dict = {"evaluated_at": datetime.now(timezone.utc).isoformat()}

    metrics["content_based"] = evaluate_recommender(
        "content_based",
        content_based_recommend_fn(cb_model),
        train_df,
        test_df,
    )

    if full_training and cf_model is not None:
        hybrid = HybridRecommender(cb_model, cf_model)
        metrics["hybrid"] = evaluate_recommender(
            "hybrid",
            hybrid_recommend_fn(hybrid),
            train_df,
            test_df,
        )

    metrics["popularity"] = evaluate_recommender(
        "popularity",
        popularity_recommend(popularity, all_content_ids),
        train_df,
        test_df,
    )
    metrics["random"] = evaluate_recommender(
        "random",
        random_recommend(all_content_ids),
        train_df,
        test_df,
    )

    return metrics


def main() -> int:
    setup_logging()
    args = parse_args()
    if args.full and args.cb_only:
        logger.error("Use only one of --full or --cb-only")
        return 1
    full_training = not args.cb_only

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Starting offline training", mode="full" if full_training else "cb-only")

    with get_session() as db:
        contents_df = load_contents_df(db)
        interactions_df = load_interactions_df(db)

    if interactions_df.empty:
        logger.error("No interactions found in database")
        return 1

    interactions_df = filter_interactions(interactions_df)
    if interactions_df.empty:
        logger.error("No interactions left after filtering")
        return 1

    train_df, test_df = split_interactions(interactions_df, test_ratio=0.2)
    logger.info(
        "Train/test split",
        train_interactions=len(train_df),
        test_interactions=len(test_df),
    )

    train_contents = enrich_contents_with_popularity(
        contents_df[contents_df["content_id"].isin(train_df["content_id"].unique())],
        train_df,
    )

    cb_model = ContentBasedRecommender()
    cb_model.fit(train_contents)
    cb_model.save(str(CB_MODEL_PATH))
    logger.info("Content-based model saved", path=str(CB_MODEL_PATH))

    cf_model: CollaborativeRecommender | None = None
    if full_training:
        als_train_df = filter_positive_interactions(train_df)
        if als_train_df.empty:
            logger.error("No positive interactions (rating_implicit >= 0.4) for ALS")
            return 1

        matrix, user_mapping, content_mapping = build_user_item_matrix(als_train_df)
        cf_model = CollaborativeRecommender()
        cf_model.fit(matrix, user_mapping, content_mapping)
        cf_model.save(str(ALS_MODEL_PATH))
        logger.info(
            "Collaborative model saved",
            path=str(ALS_MODEL_PATH),
            users=matrix.shape[0],
            items=matrix.shape[1],
            positive_interactions=len(als_train_df),
        )

        with get_session() as db:
            sync_cf_embeddings(db, cf_model)

    evaluation_metrics = run_evaluation(
        train_df=train_df,
        test_df=test_df,
        contents_df=contents_df,
        cb_model=cb_model,
        cf_model=cf_model,
        full_training=full_training,
    )

    new_version = bump_version(read_current_version())
    metrics_payload = {
        "version": new_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "mode": "full" if full_training else "cb-only",
        "train_interactions": len(train_df),
        "test_interactions": len(test_df),
        "metrics": evaluation_metrics,
    }

    METRICS_PATH.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    VERSION_PATH.write_text(f"{new_version}\n", encoding="utf-8")

    logger.info(
        "Offline training completed",
        version=new_version,
        metrics_path=str(METRICS_PATH),
        hybrid_precision=evaluation_metrics.get("hybrid", {}).get("precision@10"),
        cb_precision=evaluation_metrics["content_based"].get("precision@10"),
        popularity_precision=evaluation_metrics["popularity"].get("precision@10"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
