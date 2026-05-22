"""Business logic for recommendations and user AI profiles."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.core.cache import get_cached_recs, set_cached_recs
from app.models.hybrid import to_api_strategy
from app.models.schemas_db import Content, RecommendationEvent, UserProfileAI, ViewHistory
from app.schemas.recommendation import InteractionUpdate, RecommendationItem, RecommendationResponse
from app.services.model_loader import model_loader
from app.services.profile_updater import apply_profile_ema
from app.utils.catalog import build_contents_df
from app.utils.preprocessing import aggregate_interactions_df, compute_implicit_rating


def load_user_history(db: Session, user_id: int) -> list[tuple[int, float]]:
    rows = (
        db.query(
            ViewHistory.content_id,
            ViewHistory.completion,
            ViewHistory.started_at,
        )
        .filter(ViewHistory.user_id == user_id)
        .order_by(ViewHistory.started_at.asc())
        .all()
    )
    if not rows:
        return []

    raw = aggregate_interactions_df(
        pd.DataFrame(
            [
                {
                    "user_id": user_id,
                    "content_id": int(content_id),
                    "completion": float(completion),
                    "started_at": started_at,
                }
                for content_id, completion, started_at in rows
            ]
        )
    )
    return [
        (int(row.content_id), float(row.rating_implicit))
        for row in raw.itertuples(index=False)
    ]


def get_or_create_profile(db: Session, user_id: int) -> UserProfileAI:
    profile = db.query(UserProfileAI).filter(UserProfileAI.user_id == user_id).first()
    if profile is not None:
        return profile

    profile = UserProfileAI(
        user_id=user_id,
        genre_weights={},
        category_weights={},
        total_views=0,
        last_updated=datetime.now(timezone.utc),
    )
    db.add(profile)
    db.flush()
    return profile


async def get_recommendations(
    db: Session,
    user_id: int,
    k: int,
) -> RecommendationResponse:
    """Load history, run hybrid recommender, explain items, and cache the response."""
    if not model_loader.is_loaded or model_loader.hybrid is None:
        raise RuntimeError("Recommendation models are not loaded")

    cached = await get_cached_recs(user_id, k)
    if cached is not None:
        return RecommendationResponse.model_validate(cached)

    hybrid = model_loader.hybrid
    contents_df = build_contents_df(db)
    user_history = load_user_history(db, user_id)
    result = hybrid.recommend(user_id=user_id, user_history=user_history, k=k)

    recommendations: list[RecommendationItem] = []
    for content_id, score in result["recommendations"]:
        reason = hybrid.explain(content_id, user_history, contents_df)
        recommendations.append(
            RecommendationItem(
                content_id=content_id,
                score=score,
                reason=reason,
            )
        )

    generated_at = datetime.now(timezone.utc)
    response = RecommendationResponse(
        user_id=user_id,
        model_version=model_loader.current_model_version,
        strategy=to_api_strategy(result["strategy"]),  # type: ignore[arg-type]
        total_views=int(result["total_views"]),
        recommendations=recommendations,
        generated_at=generated_at,
    )

    _log_recommendation_events(db, user_id, recommendations, generated_at)

    await set_cached_recs(user_id, k, response.model_dump(mode="json"))
    return response


def _log_recommendation_events(
    db: Session,
    user_id: int,
    recommendations: list[RecommendationItem],
    shown_at: datetime,
) -> None:
    """Persiste eventos de recomendação para auditoria e re-treino (Seção 2.1)."""
    for item in recommendations:
        db.add(
            RecommendationEvent(
                user_id=user_id,
                content_id=item.content_id,
                score=float(item.score),
                shown_at=shown_at,
            )
        )
    db.commit()


def update_user_profile(
    db: Session,
    user_id: int,
    interaction: InteractionUpdate,
) -> UserProfileAI:
    """Persist a view interaction and update AI profile weights via EMA."""
    content = (
        db.query(Content)
        .options(
            joinedload(Content.genres),
            joinedload(Content.categories),
        )
        .filter(Content.id == interaction.content_id)
        .first()
    )
    if content is None:
        raise ValueError(f"Content {interaction.content_id} not found")

    completion = min(1.0, interaction.watched_sec / interaction.total_sec)
    prior_views = (
        db.query(ViewHistory)
        .filter(
            ViewHistory.user_id == user_id,
            ViewHistory.content_id == interaction.content_id,
        )
        .count()
    )
    rating_implicit = compute_implicit_rating(
        completion,
        revisited=prior_views > 0,
        finished=completion > 0.9,
    )
    profile = get_or_create_profile(db, user_id)
    apply_profile_ema(profile, content, rating_implicit)

    if model_loader.collaborative is not None:
        user_idx = model_loader.collaborative.user_id_to_idx.get(user_id)
        if user_idx is not None and model_loader.collaborative.model is not None:
            profile.embedding = model_loader.collaborative.model.user_factors[user_idx].tolist()

    profile.total_views = int(profile.total_views or 0) + 1
    profile.last_updated = datetime.now(timezone.utc)

    view = ViewHistory(
        user_id=user_id,
        content_id=interaction.content_id,
        watched_sec=interaction.watched_sec,
        total_sec=interaction.total_sec,
        completion=completion,
        started_at=interaction.ended_at or datetime.now(timezone.utc),
        ended_at=interaction.ended_at,
    )
    db.add(view)
    db.commit()
    db.refresh(profile)
    return profile
