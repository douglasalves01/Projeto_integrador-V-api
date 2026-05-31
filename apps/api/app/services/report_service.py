from datetime import datetime, timezone
from typing import Optional, List, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction_log import InteractionLog
from app.models.user import User
from app.models.video import Video
from app.models.watch_session import WatchSession
from app.models.video_genre import video_genre
from app.models.genre import Genre
from app.schemas.report import (
    UsageReport,
    RankedVideoReport,
    AbandonmentVideoReport,
    RankedGenreReport,
    RankedUserReport,
    UserEngagementReport,
    InsightsReport,
)


def _format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    minutes, secs = divmod(seconds, 60)
    if minutes and secs:
        return f"{minutes}min{secs:02d}s"
    if minutes:
        return f"{minutes}min"
    return f"{secs}s"


class ReportService:
    def _validate_date_range(self, start_date: Optional[datetime], end_date: Optional[datetime]):
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date range: start_date must be before end_date",
            )

    async def get_usage_report(
        self, db: AsyncSession, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> UsageReport:
        self._validate_date_range(start_date, end_date)

        # Total users
        total_users_result = await db.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar()

        # Watch sessions query with date filter
        ws_query = select(WatchSession)
        if start_date:
            ws_query = ws_query.where(WatchSession.started_at >= start_date)
        if end_date:
            ws_query = ws_query.where(WatchSession.started_at <= end_date)

        # Active users (users with at least 1 watch session in range)
        active_query = select(func.count(func.distinct(WatchSession.user_id)))
        if start_date:
            active_query = active_query.where(WatchSession.started_at >= start_date)
        if end_date:
            active_query = active_query.where(WatchSession.started_at <= end_date)
        active_result = await db.execute(active_query)
        active_users = active_result.scalar()

        # Total watch sessions
        total_sessions_query = select(func.count(WatchSession.id))
        if start_date:
            total_sessions_query = total_sessions_query.where(WatchSession.started_at >= start_date)
        if end_date:
            total_sessions_query = total_sessions_query.where(WatchSession.started_at <= end_date)
        total_sessions_result = await db.execute(total_sessions_query)
        total_sessions = total_sessions_result.scalar()

        # Average watch time
        avg_query = select(func.avg(WatchSession.watch_time_seconds))
        if start_date:
            avg_query = avg_query.where(WatchSession.started_at >= start_date)
        if end_date:
            avg_query = avg_query.where(WatchSession.started_at <= end_date)
        avg_result = await db.execute(avg_query)
        avg_watch_time = avg_result.scalar() or 0.0

        return UsageReport(
            total_users=total_users,
            active_users=active_users,
            total_watch_sessions=total_sessions,
            average_watch_time_seconds=float(avg_watch_time),
        )

    async def get_most_watched(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[RankedVideoReport]:
        self._validate_date_range(start_date, end_date)

        query = (
            select(
                WatchSession.video_id,
                Video.title,
                func.count(WatchSession.id).label("watch_count"),
            )
            .join(Video, WatchSession.video_id == Video.id)
            .group_by(WatchSession.video_id, Video.title)
            .order_by(func.count(WatchSession.id).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            RankedVideoReport(video_id=row[0], title=row[1], count=row[2])
            for row in rows
        ]

    async def get_highest_abandonment(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[AbandonmentVideoReport]:
        self._validate_date_range(start_date, end_date)

        # Calculate abandonment rate per video
        abandoned_count = func.sum(case((WatchSession.abandoned == True, 1), else_=0))
        total_count = func.count(WatchSession.id)

        query = (
            select(
                WatchSession.video_id,
                Video.title,
                (abandoned_count * 1.0 / total_count).label("abandonment_rate"),
            )
            .join(Video, WatchSession.video_id == Video.id)
            .group_by(WatchSession.video_id, Video.title)
            .having(total_count > 0)
            .order_by((abandoned_count * 1.0 / total_count).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            AbandonmentVideoReport(video_id=row[0], title=row[1], abandonment_rate=float(row[2]))
            for row in rows
        ]

    async def get_popular_genres(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[RankedGenreReport]:
        self._validate_date_range(start_date, end_date)

        query = (
            select(
                Genre.id,
                Genre.name,
                func.sum(WatchSession.watch_time_seconds).label("total_watch_time"),
            )
            .join(video_genre, Genre.id == video_genre.c.genre_id)
            .join(WatchSession, video_genre.c.video_id == WatchSession.video_id)
            .group_by(Genre.id, Genre.name)
            .order_by(func.sum(WatchSession.watch_time_seconds).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            RankedGenreReport(genre_id=row[0], name=row[1], total_watch_time_seconds=int(row[2]))
            for row in rows
        ]

    async def get_most_active_users(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[RankedUserReport]:
        self._validate_date_range(start_date, end_date)

        query = (
            select(
                User.id,
                User.name,
                User.email,
                func.count(InteractionLog.id).label("interaction_count"),
            )
            .join(InteractionLog, User.id == InteractionLog.user_id)
            .group_by(User.id, User.name, User.email)
            .order_by(func.count(InteractionLog.id).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(InteractionLog.created_at >= start_date)
        if end_date:
            query = query.where(InteractionLog.created_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            RankedUserReport(user_id=row[0], name=row[1], email=row[2], interaction_count=row[3])
            for row in rows
        ]

    async def get_user_engagement(
        self, db: AsyncSession, limit: int = 10,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[UserEngagementReport]:
        """Por usuario: sessoes, tempo total/medio assistido e retencao media."""
        self._validate_date_range(start_date, end_date)

        query = (
            select(
                User.id,
                User.name,
                User.email,
                func.count(WatchSession.id).label("sessions"),
                func.coalesce(func.sum(WatchSession.watch_time_seconds), 0).label("total_time"),
                func.coalesce(func.avg(WatchSession.watch_time_seconds), 0.0).label("avg_time"),
                func.coalesce(func.avg(WatchSession.percentage_watched), 0.0).label("avg_pct"),
            )
            .join(WatchSession, User.id == WatchSession.user_id)
            .group_by(User.id, User.name, User.email)
            .order_by(func.sum(WatchSession.watch_time_seconds).desc())
            .limit(limit)
        )

        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        result = await db.execute(query)
        rows = result.all()

        return [
            UserEngagementReport(
                user_id=row[0],
                name=row[1],
                email=row[2],
                sessions=row[3],
                total_watch_time_seconds=int(row[4]),
                average_watch_time_seconds=float(row[5]),
                average_percentage_watched=float(row[6]),
            )
            for row in rows
        ]

    async def _get_retention_overview(
        self, db: AsyncSession,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Tuple[float, float]:
        """Retorna (retencao_media_pct, taxa_conclusao_pct) das watch_sessions."""
        completed_count = func.sum(case((WatchSession.completed == True, 1), else_=0))
        total_count = func.count(WatchSession.id)
        query = select(
            func.coalesce(func.avg(WatchSession.percentage_watched), 0.0),
            func.coalesce(completed_count, 0),
            total_count,
        )
        if start_date:
            query = query.where(WatchSession.started_at >= start_date)
        if end_date:
            query = query.where(WatchSession.started_at <= end_date)

        avg_pct, completed, total = (await db.execute(query)).one()
        avg_pct = float(avg_pct or 0.0)
        completion_rate = (float(completed) / total) if total else 0.0
        return avg_pct, completion_rate

    async def get_insights(
        self, db: AsyncSession, limit: int = 5,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> InsightsReport:
        """Resumo executivo: agrega as metricas e monta um texto de insights.

        O texto e gerado a partir dos numeros reais (deterministico) — nao usa
        LLM, para nao correr risco de inventar estatisticas.
        """
        self._validate_date_range(start_date, end_date)

        usage = await self.get_usage_report(db, start_date, end_date)
        most_watched = await self.get_most_watched(db, limit, start_date, end_date)
        abandonment = await self.get_highest_abandonment(db, limit, start_date, end_date)
        genres = await self.get_popular_genres(db, limit, start_date, end_date)
        top_users = await self.get_user_engagement(db, limit, start_date, end_date)
        avg_pct, completion_rate = await self._get_retention_overview(db, start_date, end_date)

        highlights: List[str] = []

        if usage.total_watch_sessions == 0:
            headline = "Sem visualizações registradas no período."
            highlights.append(
                "Nenhuma watch session encontrada. Verifique o filtro de datas "
                "ou se há atividade de usuários no período."
            )
        else:
            active_pct = (
                (usage.active_users / usage.total_users * 100) if usage.total_users else 0.0
            )
            headline = (
                f"{usage.total_watch_sessions} visualizações de {usage.active_users} "
                f"usuários ativos, com {_format_duration(usage.average_watch_time_seconds)} "
                "em média por sessão."
            )

            highlights.append(
                f"Engajamento: {usage.active_users}/{usage.total_users} usuários ativos "
                f"({active_pct:.0f}%) somaram {usage.total_watch_sessions} sessões de visualização."
            )
            highlights.append(
                f"Tempo médio assistido por sessão: {_format_duration(usage.average_watch_time_seconds)}; "
                f"retenção média de {avg_pct * 100:.0f}% do vídeo e "
                f"{completion_rate * 100:.0f}% das sessões concluídas até o fim."
            )

            if most_watched:
                top = most_watched[0]
                highlights.append(
                    f"Vídeo mais assistido: \"{top.title}\" com {top.count} visualizações."
                )
            if genres:
                g = genres[0]
                highlights.append(
                    f"Gênero que mais prende: \"{g.name}\" lidera em tempo assistido "
                    f"({_format_duration(g.total_watch_time_seconds)} no total)."
                )
            if abandonment and abandonment[0].abandonment_rate > 0:
                ab = abandonment[0]
                highlights.append(
                    f"Atenção: \"{ab.title}\" tem a maior taxa de abandono "
                    f"({ab.abandonment_rate * 100:.0f}%) — candidato a revisão."
                )
            if top_users:
                u = top_users[0]
                highlights.append(
                    f"Usuário mais engajado: {u.name} — {u.sessions} sessões, "
                    f"{_format_duration(u.total_watch_time_seconds)} assistidos "
                    f"(retenção média {u.average_percentage_watched * 100:.0f}%)."
                )

        return InsightsReport(
            generated_at=datetime.now(timezone.utc),
            period_start=start_date,
            period_end=end_date,
            headline=headline,
            highlights=highlights,
            usage=usage,
            average_percentage_watched=avg_pct,
            completion_rate=completion_rate,
            most_watched=most_watched,
            highest_abandonment=abandonment,
            popular_genres=genres,
            top_users=top_users,
        )
