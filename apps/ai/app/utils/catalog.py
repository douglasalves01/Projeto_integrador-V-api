"""Helpers to build catalog DataFrames from the database."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.models.schemas_db import Content
from app.utils.preprocessing import build_text_doc


def build_contents_df(db: Session) -> pd.DataFrame:
    """Build a catalog DataFrame for content-based explain and inference."""
    contents = (
        db.query(Content)
        .options(
            joinedload(Content.genres),
            joinedload(Content.categories),
        )
        .all()
    )

    rows: list[dict] = []
    for content in contents:
        genre_names = [genre.name for genre in content.genres]
        category_names = [category.name for category in content.categories]

        rows.append(
            {
                "content_id": content.id,
                "text_doc": build_text_doc(
                    content.title,
                    content.description,
                    genre_names,
                    category_names,
                ),
                "genres": ",".join(genre_names),
                "categories": ",".join(category_names),
            }
        )

    return pd.DataFrame(rows)
