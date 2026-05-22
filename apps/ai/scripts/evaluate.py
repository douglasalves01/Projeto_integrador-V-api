#!/usr/bin/env python3
"""Evaluate loaded models against a held-out test split with comparative metrics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import setup_logging  # noqa: E402
from app.services.model_loader import model_loader  # noqa: E402
from app.utils.metrics import evaluate_recommender  # noqa: E402
from scripts.evaluation import (  # noqa: E402
    content_based_recommend_fn,
    hybrid_recommend_fn,
    popularity_recommend,
    random_recommend,
    split_interactions,
)
from scripts.feature_extractor import get_session, load_interactions_df  # noqa: E402
from scripts.train_offline import (  # noqa: E402
    MIN_CONTENT_INTERACTIONS,
    MIN_USER_INTERACTIONS,
    filter_interactions,
)

RFIA01_HIT_RATE_TARGET = 0.70


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate recommendation models")
    parser.add_argument("--k", type=int, default=10, help="Metric cutoff (default: 10)")
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.2,
        help="Fraction of most recent interactions per user for testing",
    )
    return parser.parse_args()


def _metric_value(metrics: dict[str, float], base: str, k: int) -> float:
    return float(metrics.get(f"{base}@{k}", 0.0))


def _format_row(model_name: str, metrics: dict[str, float], k: int) -> dict[str, str | float]:
    return {
        "Model": model_name,
        "P@10": _metric_value(metrics, "precision", k),
        "R@10": _metric_value(metrics, "recall", k),
        "HitRate@10": _metric_value(metrics, "hit_rate", k),
        "NDCG@10": _metric_value(metrics, "ndcg", k),
        "MAP@10": _metric_value(metrics, "map", k),
    }


def print_comparison_table(rows: list[dict[str, str | float]], k: int) -> None:
    headers = ["Model", f"P@{k}", f"R@{k}", f"HitRate@{k}", f"NDCG@{k}", f"MAP@{k}"]
    col_keys = ["Model", "P@10", "R@10", "HitRate@10", "NDCG@10", "MAP@10"]

    widths = {header: len(header) for header in headers}
    for row in rows:
        for header, key in zip(headers, col_keys):
            if key == "Model":
                widths[header] = max(widths[header], len(str(row[key])))
            else:
                widths[header] = max(widths[header], len(f"{float(row[key]):.3f}"))

    def fmt_row(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[headers[i]]) for i, value in enumerate(values))

    separator = "-+-".join("-" * widths[h] for h in headers)
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        formatted = [
            str(row["Model"]),
            f"{float(row['P@10']):.3f}",
            f"{float(row['R@10']):.3f}",
            f"{float(row['HitRate@10']):.3f}",
            f"{float(row['NDCG@10']):.3f}",
            f"{float(row['MAP@10']):.3f}",
        ]
        print(fmt_row(formatted))


def collaborative_recommend_fn(cf_model) -> callable:
    def _recommend(user_id: int, history: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
        del history
        return cf_model.recommend(user_id, k=k, exclude_seen=True)

    return _recommend


def main() -> int:
    setup_logging()
    args = parse_args()
    k = args.k

    if not model_loader.load():
        logger.error("Failed to load models from disk")
        return 1

    logger.info(
        "Models loaded for evaluation",
        version=model_loader.current_model_version,
    )

    with get_session() as db:
        interactions_df = load_interactions_df(db)

    if interactions_df.empty:
        logger.error("No interactions available for evaluation")
        return 1

    interactions_df = filter_interactions(interactions_df)
    train_df, test_df = split_interactions(interactions_df, test_ratio=args.test_ratio)

    logger.info(
        "Evaluation split ready",
        train=len(train_df),
        test=len(test_df),
        users_test=int(test_df["user_id"].nunique()),
    )

    all_content_ids = sorted(interactions_df["content_id"].astype(int).unique().tolist())
    popularity = train_df.groupby("content_id").size().astype(float).to_dict()

    evaluators: list[tuple[str, object]] = []

    if model_loader.hybrid and model_loader.content_based and model_loader.collaborative:
        evaluators.append(("Hybrid", hybrid_recommend_fn(model_loader.hybrid)))
        evaluators.append(("ContentBased", content_based_recommend_fn(model_loader.content_based)))
        evaluators.append(("Collaborative", collaborative_recommend_fn(model_loader.collaborative)))
    else:
        logger.warning("Some models missing; skipping model-specific evaluators")

    evaluators.extend(
        [
            ("Popularity", popularity_recommend(popularity, all_content_ids)),
            ("Random", random_recommend(all_content_ids)),
        ]
    )

    table_rows: list[dict[str, str | float]] = []
    for model_name, recommender in evaluators:
        metrics = evaluate_recommender(
            recommender=recommender,
            test_interactions=test_df,
            train_interactions=train_df,
            k=k,
        )
        logger.info("Evaluation finished", model=model_name, **{key: round(val, 4) for key, val in metrics.items() if "@" in key})
        table_rows.append(_format_row(model_name, metrics, k))

    print()
    print_comparison_table(table_rows, k=k)
    print()

    hybrid_row = next((row for row in table_rows if row["Model"] == "Hybrid"), None)
    if hybrid_row is not None:
        hit_rate = float(hybrid_row["HitRate@10"])
        target = RFIA01_HIT_RATE_TARGET
        status = "PASS" if hit_rate >= target else "FAIL"
        print(f"RFIA01 HitRate@{k} >= {target:.2f}: {status} (Hybrid HitRate@{k} = {hit_rate:.3f})")
    else:
        print("RFIA01: Hybrid model not evaluated (models not loaded)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
