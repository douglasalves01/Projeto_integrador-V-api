import pandas as pd

from scripts.evaluation import (
    evaluate_recommender,
    popularity_recommend,
    random_recommend,
    split_interactions,
)


def test_split_interactions_temporal() -> None:
    n = 12  # RFIA01: usuários com >=10 interações
    df = pd.DataFrame(
        {
            "user_id": [1] * n,
            "content_id": list(range(10, 10 + n)),
            "rating_implicit": [1.0] * n,
            "started_at": pd.date_range("2024-01-01", periods=n, freq="D"),
        }
    )
    train_df, test_df = split_interactions(df, test_ratio=0.2)
    assert len(test_df) >= 1
    assert int(test_df.iloc[-1]["content_id"]) == 10 + n - 1
    assert len(train_df) + len(test_df) == n


def test_popularity_beats_random_on_toy_data() -> None:
    train_df = pd.DataFrame(
        {
            "user_id": [1, 1, 1, 2, 2, 2],
            "content_id": [10, 10, 11, 10, 12, 12],
            "rating_implicit": [1.0, 0.9, 0.8, 1.0, 0.5, 0.4],
            "started_at": pd.date_range("2024-01-01", periods=6, freq="D"),
        }
    )
    test_df = pd.DataFrame(
        {
            "user_id": [1, 2],
            "content_id": [10, 12],
            "rating_implicit": [1.0, 1.0],
            "started_at": pd.to_datetime(["2024-02-01", "2024-02-02"]),
        }
    )

    popularity = train_df.groupby("content_id").size().astype(float).to_dict()
    pop_metrics = evaluate_recommender(
        "popularity",
        popularity_recommend(popularity, [10, 11, 12]),
        train_df,
        test_df,
        k=2,
    )
    rand_metrics = evaluate_recommender(
        "random",
        random_recommend([10, 11, 12], seed=1),
        train_df,
        test_df,
        k=2,
    )

    assert pop_metrics["hit_rate@2"] >= rand_metrics["hit_rate@2"]
