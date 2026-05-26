import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.interaction_log import InteractionLog, InteractionType
from app.models.recommendation import Recommendation
from app.models.video import Video
from app.models.watch_session import WatchSession
from app.models.video_genre import video_genre
from app.models.video_category import video_category
from app.repositories.interaction_log_repository import InteractionLogRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.video_repository import VideoRepository
from app.repositories.watch_session_repository import WatchSessionRepository

logger = logging.getLogger(__name__)

# Scoring weights
GENRE_AFFINITY_WEIGHT = 0.30
CATEGORY_AFFINITY_WEIGHT = 0.20
COMPLETION_RATE_WEIGHT = 0.15
POPULARITY_WEIGHT = 0.15
SEARCH_RELEVANCE_WEIGHT = 0.10
RECENCY_WEIGHT = 0.10

ABANDONMENT_PENALTY = 0.5
MIN_INTERACTIONS_FOR_PERSONALIZED = 5


class RecommendationService:
    def __init__(self):
        self.interaction_repo = InteractionLogRepository()
        self.recommendation_repo = RecommendationRepository()
        self.video_repo = VideoRepository()
        self.session_repo = WatchSessionRepository()

    async def get_recommendations(
        self,
        db: AsyncSession,
        user_id: UUID,
        jwt: str | None = None,
    ) -> List[Recommendation]:
        if jwt:
            try:
                from app.integrations.ai_client import get_ai_client

                ai_client = get_ai_client()
                if ai_client is not None and ai_client.available:
                    payload = await ai_client.get_recommendations(user_id, jwt=jwt, k=10)
                    if payload and payload.get("recommendations"):
                        ai_recommendations = await self._materialize_ai_recommendations(
                            db, user_id, payload
                        )
                        if ai_recommendations:
                            logger.info(
                                "Recommendations served by AI (%s)",
                                payload.get("model_version"),
                            )
                            return ai_recommendations
            except Exception as exc:
                logger.warning("AI fallback triggered: %s", exc)

        # Count user interactions
        interaction_count = await self.interaction_repo.count_user_interactions(db, user_id)

        # Get completed video IDs to exclude
        completed_ids = await self.session_repo.get_completed_video_ids_for_user(db, user_id)

        if interaction_count < MIN_INTERACTIONS_FOR_PERSONALIZED:
            # Fallback: popularity-based
            return await self._popularity_based_recommendations(db, user_id, completed_ids)

        # Personalized recommendations
        return await self._personalized_recommendations(db, user_id, completed_ids)

    async def _materialize_ai_recommendations(
        self,
        db: AsyncSession,
        user_id: UUID,
        payload: dict,
    ) -> List[Recommendation]:
        items = payload.get("recommendations", [])
        if not items:
            return []

        requested_video_ids: set[UUID] = set()
        for item in items:
            try:
                requested_video_ids.add(UUID(str(item["content_id"])))
            except (KeyError, ValueError):
                continue

        if not requested_video_ids:
            return []

        existing_result = await db.execute(
            select(Video.id).where(Video.id.in_(requested_video_ids))
        )
        existing_ids = {row[0] for row in existing_result.all()}
        if not existing_ids:
            return []

        await self.recommendation_repo.delete_user_recommendations(db, user_id)
        output: List[Recommendation] = []
        for item in items:
            try:
                video_id = UUID(str(item["content_id"]))
                score = float(item.get("score", 0.0))
            except (KeyError, ValueError, TypeError):
                continue

            if video_id not in existing_ids:
                continue

            recommendation = Recommendation(
                user_id=user_id,
                video_id=video_id,
                relevance_score=score,
                explanation=item.get("reason") or payload.get("strategy", "ai"),
            )
            db.add(recommendation)
            output.append(recommendation)

        await db.flush()
        return output

    async def _popularity_based_recommendations(
        self, db: AsyncSession, user_id: UUID, exclude_ids: List[UUID]
    ) -> List[Recommendation]:
        videos = await self.video_repo.get_popular_videos(db, limit=10, exclude_video_ids=exclude_ids)

        # Delete old recommendations for user
        await self.recommendation_repo.delete_user_recommendations(db, user_id)

        recommendations = []
        for i, video in enumerate(videos):
            score = 1.0 - (i * 0.05)  # Decreasing score by rank
            rec = Recommendation(
                user_id=user_id,
                video_id=video.id,
                relevance_score=round(score, 4),
                explanation="Recommended based on popularity among all users.",
            )
            recommendations.append(rec)

        if recommendations:
            await self.recommendation_repo.create_many(db, recommendations)

        return recommendations

    async def _personalized_recommendations(
        self, db: AsyncSession, user_id: UUID, completed_ids: List[UUID]
    ) -> List[Recommendation]:
        # Get user interactions
        interactions = await self.interaction_repo.get_user_interactions(db, user_id)

        # Get user watch sessions
        result = await db.execute(
            select(WatchSession).where(WatchSession.user_id == user_id)
        )
        watch_sessions = list(result.scalars().all())

        # Compute genre scores
        genre_scores = await self._compute_genre_affinity(db, watch_sessions)

        # Compute category scores
        category_scores = await self._compute_category_affinity(db, watch_sessions)

        # Compute completion rates per genre/category
        completion_rates = self._compute_completion_rates(watch_sessions)

        # Compute search relevance
        search_scores = self._compute_search_relevance(interactions)

        # Compute abandonment rates for negative signals
        abandonment_rates = self._compute_abandonment_rates(watch_sessions)

        # Compute recency scores
        recency_scores = self._compute_recency(interactions)

        # Get candidate videos (exclude completed)
        result = await db.execute(
            select(Video)
            .options(selectinload(Video.genres), selectinload(Video.categories))
            .where(Video.id.notin_(completed_ids) if completed_ids else True)
        )
        candidates = list(result.scalars().unique().all())

        # Compute popularity for each video
        popularity_scores = await self._compute_popularity(db)

        # Score each candidate
        scored_videos = []
        for video in candidates:
            score = self._score_video(
                video, genre_scores, category_scores, completion_rates,
                popularity_scores, search_scores, recency_scores, abandonment_rates
            )
            explanation = self._generate_explanation(
                video, genre_scores, category_scores, popularity_scores, search_scores
            )
            scored_videos.append((video, score, explanation))

        # Sort by score descending and take top 10
        scored_videos.sort(key=lambda x: x[1], reverse=True)
        top_10 = scored_videos[:10]

        # Delete old recommendations
        await self.recommendation_repo.delete_user_recommendations(db, user_id)

        # Create new recommendations
        recommendations = []
        for video, score, explanation in top_10:
            rec = Recommendation(
                user_id=user_id,
                video_id=video.id,
                relevance_score=round(score, 4),
                explanation=explanation,
            )
            recommendations.append(rec)

        if recommendations:
            await self.recommendation_repo.create_many(db, recommendations)

        return recommendations

    async def _compute_genre_affinity(
        self, db: AsyncSession, watch_sessions: List[WatchSession]
    ) -> Dict[UUID, float]:
        """Proportion of watch time per genre."""
        genre_watch_time: Dict[UUID, int] = defaultdict(int)
        total_watch_time = 0

        for session in watch_sessions:
            if session.watch_time_seconds > 0:
                # Get genres for this video
                result = await db.execute(
                    select(video_genre.c.genre_id).where(
                        video_genre.c.video_id == session.video_id
                    )
                )
                genre_ids = [row[0] for row in result.all()]
                for gid in genre_ids:
                    genre_watch_time[gid] += session.watch_time_seconds
                total_watch_time += session.watch_time_seconds

        if total_watch_time == 0:
            return {}

        return {gid: wt / total_watch_time for gid, wt in genre_watch_time.items()}

    async def _compute_category_affinity(
        self, db: AsyncSession, watch_sessions: List[WatchSession]
    ) -> Dict[UUID, float]:
        """Average watch time per category."""
        category_watch_time: Dict[UUID, List[int]] = defaultdict(list)

        for session in watch_sessions:
            if session.watch_time_seconds > 0:
                result = await db.execute(
                    select(video_category.c.category_id).where(
                        video_category.c.video_id == session.video_id
                    )
                )
                cat_ids = [row[0] for row in result.all()]
                for cid in cat_ids:
                    category_watch_time[cid].append(session.watch_time_seconds)

        if not category_watch_time:
            return {}

        max_avg = max(
            sum(times) / len(times) for times in category_watch_time.values()
        )
        if max_avg == 0:
            return {}

        return {
            cid: (sum(times) / len(times)) / max_avg
            for cid, times in category_watch_time.items()
        }

    def _compute_completion_rates(self, watch_sessions: List[WatchSession]) -> Dict[UUID, float]:
        """Completion rate per video_id."""
        video_sessions: Dict[UUID, List[bool]] = defaultdict(list)
        for session in watch_sessions:
            video_sessions[session.video_id].append(session.completed)

        return {
            vid: sum(1 for c in completions if c) / len(completions)
            for vid, completions in video_sessions.items()
        }

    def _compute_search_relevance(self, interactions: List[InteractionLog]) -> Dict[str, int]:
        """Frequency of search terms."""
        search_counts: Dict[str, int] = defaultdict(int)
        for interaction in interactions:
            if interaction.interaction_type == InteractionType.SEARCH and interaction.search_query:
                search_counts[interaction.search_query.lower()] += 1
        return search_counts

    def _compute_abandonment_rates(self, watch_sessions: List[WatchSession]) -> Dict[UUID, float]:
        """Abandonment rate per genre (via video_id for now)."""
        video_abandonment: Dict[UUID, List[bool]] = defaultdict(list)
        for session in watch_sessions:
            video_abandonment[session.video_id].append(session.abandoned)

        return {
            vid: sum(1 for a in abandonments if a) / len(abandonments)
            for vid, abandonments in video_abandonment.items()
        }

    def _compute_recency(self, interactions: List[InteractionLog]) -> float:
        """Recency factor based on most recent interaction."""
        if not interactions:
            return 0.0
        most_recent = max(i.created_at for i in interactions)
        days_ago = (datetime.utcnow() - most_recent).days
        # Decay: 1.0 for today, decreasing over 30 days
        return max(0.0, 1.0 - (days_ago / 30.0))

    async def _compute_popularity(self, db: AsyncSession) -> Dict[UUID, float]:
        """Total watch count per video, normalized."""
        result = await db.execute(
            select(WatchSession.video_id, func.count(WatchSession.id))
            .group_by(WatchSession.video_id)
        )
        counts = {row[0]: row[1] for row in result.all()}
        if not counts:
            return {}
        max_count = max(counts.values())
        if max_count == 0:
            return {}
        return {vid: count / max_count for vid, count in counts.items()}

    def _score_video(
        self,
        video: Video,
        genre_scores: Dict[UUID, float],
        category_scores: Dict[UUID, float],
        completion_rates: Dict[UUID, float],
        popularity_scores: Dict[UUID, float],
        search_scores: Dict[str, int],
        recency_score: float,
        abandonment_rates: Dict[UUID, float],
    ) -> float:
        # Genre affinity
        genre_score = 0.0
        if video.genres:
            genre_vals = [genre_scores.get(g.id, 0.0) for g in video.genres]
            genre_score = max(genre_vals) if genre_vals else 0.0

        # Category affinity
        category_score = 0.0
        if video.categories:
            cat_vals = [category_scores.get(c.id, 0.0) for c in video.categories]
            category_score = max(cat_vals) if cat_vals else 0.0

        # Completion rate
        completion_score = completion_rates.get(video.id, 0.0)

        # Popularity
        popularity_score = popularity_scores.get(video.id, 0.0)

        # Search relevance (check if video title words appear in searches)
        search_score = 0.0
        if search_scores:
            title_words = video.title.lower().split()
            for word in title_words:
                if word in search_scores:
                    search_score = min(1.0, search_scores[word] / 5.0)
                    break

        # Weighted sum
        total_score = (
            genre_score * GENRE_AFFINITY_WEIGHT
            + category_score * CATEGORY_AFFINITY_WEIGHT
            + completion_score * COMPLETION_RATE_WEIGHT
            + popularity_score * POPULARITY_WEIGHT
            + search_score * SEARCH_RELEVANCE_WEIGHT
            + recency_score * RECENCY_WEIGHT
        )

        # Apply negative signal (abandonment penalty)
        abandonment_rate = abandonment_rates.get(video.id, 0.0)
        if abandonment_rate > 0.5:
            total_score *= ABANDONMENT_PENALTY

        return total_score

    def _generate_explanation(
        self,
        video: Video,
        genre_scores: Dict[UUID, float],
        category_scores: Dict[UUID, float],
        popularity_scores: Dict[UUID, float],
        search_scores: Dict[str, int],
    ) -> str:
        factors = []

        # Check genre affinity
        if video.genres:
            for g in video.genres:
                if genre_scores.get(g.id, 0) > 0.1:
                    factors.append(f"genre affinity ({g.name})")
                    break

        # Check category affinity
        if video.categories:
            for c in video.categories:
                if category_scores.get(c.id, 0) > 0.1:
                    factors.append(f"category preference ({c.name})")
                    break

        # Check popularity
        if popularity_scores.get(video.id, 0) > 0.3:
            factors.append("popularity")

        # Check search history
        if search_scores:
            title_words = video.title.lower().split()
            for word in title_words:
                if word in search_scores:
                    factors.append("search history")
                    break

        if not factors:
            factors.append("watch history")

        return "Recommended based on: " + ", ".join(factors) + "."

    async def get_all_recommendations_paginated(
        self, db: AsyncSession, page: int, page_size: int
    ):
        return await self.recommendation_repo.get_all_paginated(db, page, page_size)
