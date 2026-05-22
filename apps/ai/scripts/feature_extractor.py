"""Backward-compatible re-exports — use ``app.services.feature_extractor``."""

from app.services.feature_extractor import (  # noqa: F401
    get_session,
    load_contents_df,
    load_interactions_df,
)

__all__ = ["get_session", "load_contents_df", "load_interactions_df"]
