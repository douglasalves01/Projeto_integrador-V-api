"""Tests for implicit rating and text document preprocessing."""

import pandas as pd
import pytest

from app.utils.preprocessing import (
    POSITIVE_INTERACTION_THRESHOLD,
    aggregate_interactions_df,
    build_text_doc,
    compute_implicit_rating,
    filter_positive_interactions,
)


class TestImplicitRating:
    def test_formula_completion_only(self) -> None:
        assert compute_implicit_rating(1.0, revisited=False, finished=True) == pytest.approx(0.7)

    def test_formula_with_revisit(self) -> None:
        assert compute_implicit_rating(0.5, revisited=True, finished=False) == pytest.approx(0.6)

    def test_clips_to_unit_interval(self) -> None:
        assert compute_implicit_rating(2.0) == 1.0
        assert compute_implicit_rating(-1.0) == 0.0


class TestTextDoc:
    def test_genres_repeated_three_times(self) -> None:
        doc = build_text_doc("Título", "desc", ["Ação"], ["Documentário"])
        assert doc.count("Ação") == 3
        assert doc.count("Documentário") == 3
        assert "Título" in doc


class TestAggregateInteractions:
    def test_revisit_increases_rating(self) -> None:
        df = pd.DataFrame(
            [
                {"user_id": 1, "content_id": 10, "completion": 0.5, "started_at": "2026-01-01"},
                {"user_id": 1, "content_id": 10, "completion": 0.5, "started_at": "2026-01-02"},
            ]
        )
        agg = aggregate_interactions_df(df)
        single = compute_implicit_rating(0.5, revisited=False, finished=False)
        assert float(agg.iloc[0]["rating_implicit"]) > single

    def test_positive_filter(self) -> None:
        df = pd.DataFrame(
            [
                {"user_id": 1, "content_id": 1, "completion": 0.1, "started_at": "2026-01-01"},
                {"user_id": 1, "content_id": 2, "completion": 0.9, "started_at": "2026-01-02"},
            ]
        )
        positive = filter_positive_interactions(aggregate_interactions_df(df))
        assert (positive["rating_implicit"] >= POSITIVE_INTERACTION_THRESHOLD).all()
        assert len(positive) == 1
