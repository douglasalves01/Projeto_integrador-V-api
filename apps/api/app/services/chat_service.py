"""Orquestra VodChat + busca de vídeos para POST /chat."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.video import Video
from app.schemas.chat import ChatResponse, ChatVideoSuggestion
from app.services.chat_intent import (
    CATALOG_CATEGORIES,
    expand_topic_keywords,
    extract_search_query,
    is_out_of_catalog_genre,
    should_attach_videos,
    should_use_personalized_recommendations,
    topic_keywords,
    video_matches_topic,
)
from app.services.video_service import VideoService

logger = logging.getLogger(__name__)

FALLBACK_REPLY = (
    "Desculpe, o assistente esta temporariamente indisponivel. "
    "Tente novamente em instantes."
)
_URL_PATTERN = re.compile(r"https?://|www\.|youtube\.com|youtu\.be", re.IGNORECASE)
_ENGLISH_HINTS = re.compile(
    r"\b(sure|here are|i can provide|dear |hello |hi there|watch this)\b",
    re.IGNORECASE,
)


class ChatService:
    def __init__(self) -> None:
        self.video_service = VideoService()
        from app.services.recommendation_service import RecommendationService

        self.recommendation_service = RecommendationService()

    async def handle(
        self,
        db: AsyncSession,
        user_id: UUID,
        message: str,
        jwt: str | None,
    ) -> ChatResponse:
        started = time.perf_counter()

        # Pedidos abertos ("o que ver com a namorada?") — recomendacoes personalizadas.
        if should_use_personalized_recommendations(message):
            personalized = await self._fetch_personalized_suggestions(
                db, user_id, jwt
            )
            if personalized:
                response = ChatResponse(
                    reply=_recommendation_reply(personalized, message),
                    fallback=False,
                    videos=personalized,
                    search_query=None,
                    catalog_empty=False,
                )
                logger.info(
                    "Chat request completed (personalized-fast-path) user_id=%s fallback=%s videos=%d catalog_empty=%s latency_ms=%.2f",
                    user_id,
                    response.fallback,
                    len(response.videos),
                    response.catalog_empty,
                    (time.perf_counter() - started) * 1000,
                )
                return response

        attach_videos = (
            settings.CHAT_ATTACH_VIDEOS and should_attach_videos(message)
        )
        search_query = extract_search_query(message) if attach_videos else None
        logger.info(
            "Chat request started user_id=%s attach_videos=%s search_query=%r",
            user_id,
            attach_videos,
            search_query,
        )

        # Pedido de genero de filme/serie que nao existe no acervo educativo:
        # responde com honestidade, sem chamar IA nem empurrar vizinhos semanticos.
        if search_query and is_out_of_catalog_genre(search_query):
            logger.info(
                "Chat request out-of-catalog genre user_id=%s search_query=%r",
                user_id,
                search_query,
            )
            return ChatResponse(
                reply=_out_of_catalog_reply(search_query),
                fallback=False,
                videos=[],
                search_query=search_query,
                catalog_empty=True,
            )

        videos: list[ChatVideoSuggestion] = []
        try:
            videos = (
                await asyncio.wait_for(
                    self._fetch_video_suggestions(db, search_query),
                    timeout=settings.CHAT_VIDEO_SEARCH_TIMEOUT_SEC,
                )
                if attach_videos and search_query
                else []
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Chat video search timed out user_id=%s search_query=%r timeout_sec=%s",
                user_id,
                search_query,
                settings.CHAT_VIDEO_SEARCH_TIMEOUT_SEC,
            )
            videos = []

        # Fast-path: quando a resposta será baseada no catálogo, não espere o LLM.
        if videos and settings.CHAT_PREFER_CATALOG_REPLY:
            response = self._build_response(
                reply=None,
                fallback=False,
                videos=videos,
                search_query=search_query,
            )
            logger.info(
                "Chat request completed (catalog-fast-path) user_id=%s fallback=%s videos=%d catalog_empty=%s latency_ms=%.2f",
                user_id,
                response.fallback,
                len(response.videos),
                response.catalog_empty,
                (time.perf_counter() - started) * 1000,
            )
            return response

        vodchat_task = asyncio.create_task(
            self._fetch_vodchat_reply(user_id, message, jwt)
        )
        try:
            reply, fallback = await asyncio.wait_for(
                vodchat_task,
                timeout=settings.CHAT_VODCHAT_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "VodChat timed out user_id=%s timeout_sec=%s",
                user_id,
                settings.CHAT_VODCHAT_TIMEOUT_SEC,
            )
            reply, fallback = None, True

        response = self._build_response(
            reply=reply,
            fallback=fallback,
            videos=videos,
            search_query=search_query,
        )
        logger.info(
            "Chat request completed user_id=%s fallback=%s videos=%d catalog_empty=%s latency_ms=%.2f",
            user_id,
            response.fallback,
            len(response.videos),
            response.catalog_empty,
            (time.perf_counter() - started) * 1000,
        )
        return response

    async def _fetch_vodchat_reply(
        self,
        user_id: UUID,
        message: str,
        jwt: str | None,
    ) -> tuple[str | None, bool]:
        if not jwt:
            logger.warning("VodChat skipped because JWT was not forwarded user_id=%s", user_id)
            return None, True
        try:
            from app.integrations.ai_client import get_ai_client

            ai = get_ai_client()
            if ai is None or not ai.available:
                logger.warning("VodChat skipped because AI client is unavailable user_id=%s", user_id)
                return None, True
            reply = await ai.chat(user_id, jwt=jwt, message=message)
            if reply and reply.strip():
                logger.info("VodChat reply received user_id=%s chars=%d", user_id, len(reply))
                return reply.strip(), False
        except Exception as exc:
            logger.warning("VodChat unavailable: %s", exc)
        return None, True

    async def _fetch_video_suggestions(
        self,
        db: AsyncSession,
        search_query: str,
    ) -> list[ChatVideoSuggestion]:
        try:
            limit = settings.CHAT_VIDEO_SUGGESTIONS_LIMIT
            keywords = expand_topic_keywords(search_query)

            # Para temas conhecidos, a busca textual por palavras-chave e mais rapida
            # e evita que embeddings lentos bloqueiem a resposta do chat.
            if keywords:
                by_keywords = await self.video_service.search_videos_by_topic_keywords(
                    db, keywords, limit
                )
                if by_keywords:
                    return [_video_to_suggestion(video) for video in by_keywords]

            if settings.CHAT_SEMANTIC_SEARCH_ON_CHAT and settings.SEMANTIC_SEARCH_ENABLED:
                videos = await self._semantic_chat_search(
                    db, search_query, keywords, limit
                )
            else:
                videos, _total = await self.video_service.search_videos(
                    db,
                    query=search_query,
                    page=1,
                    page_size=limit,
                    semantic=False,
                )
                if settings.CHAT_REQUIRE_TOPIC_KEYWORD_MATCH and keywords:
                    videos = [
                        v
                        for v in videos
                        if video_matches_topic(v.title, v.description, keywords)
                    ][:limit]

            return [_video_to_suggestion(video) for video in videos]
        except Exception as exc:
            logger.warning("Chat video search failed: %s", exc)
            return []

    async def _fetch_personalized_suggestions(
        self,
        db: AsyncSession,
        user_id: UUID,
        jwt: str | None,
    ) -> list[ChatVideoSuggestion]:
        try:
            limit = settings.CHAT_VIDEO_SUGGESTIONS_LIMIT
            recs = await self.recommendation_service.get_recommendations(
                db,
                user_id,
                jwt=jwt,
            )
            suggestions: list[ChatVideoSuggestion] = []
            for rec in recs[:limit]:
                video = await self.video_service.get_video_for_watch(db, rec.video_id)
                suggestions.append(_video_to_suggestion(video))
            return suggestions
        except Exception as exc:
            logger.warning("Personalized chat suggestions failed: %s", exc)
            return []

    async def _semantic_chat_search(
        self,
        db: AsyncSession,
        search_query: str,
        keywords: list[str],
        limit: int,
    ) -> list[Video]:
        scored = await self.video_service.search_videos_semantic_scored(
            db,
            search_query,
            limit=settings.CHAT_VIDEO_CANDIDATE_LIMIT,
            max_distance=settings.CHAT_SEMANTIC_MAX_DISTANCE,
        )
        videos = _filter_scored_videos(scored, keywords, limit)
        if videos:
            return videos

        scored = await self.video_service.search_videos_semantic_scored(
            db,
            search_query,
            limit=settings.CHAT_VIDEO_CANDIDATE_LIMIT,
            max_distance=None,
        )
        videos = _filter_scored_videos(scored, keywords, limit)
        if videos:
            return videos

        # Fallback: titulo/descricao (receita, cozinha...) — "culinaria" raramente esta no titulo.
        if keywords:
            by_keywords = await self.video_service.search_videos_by_topic_keywords(
                db, keywords, limit
            )
            if by_keywords:
                return by_keywords

        return []

    def _build_response(
        self,
        *,
        reply: str | None,
        fallback: bool,
        videos: list[ChatVideoSuggestion],
        search_query: str | None,
    ) -> ChatResponse:
        if videos:
            prefer_catalog = settings.CHAT_PREFER_CATALOG_REPLY or _is_unusable_vodchat_reply(
                reply or ""
            )
            text = (
                _catalog_reply(videos, search_query)
                if prefer_catalog
                else (reply or _catalog_reply(videos, search_query))
            )
            return ChatResponse(
                reply=text,
                fallback=fallback,
                videos=videos,
                search_query=search_query,
                catalog_empty=False,
            )

        if search_query:
            return ChatResponse(
                reply=_empty_catalog_reply(search_query),
                fallback=False,
                videos=[],
                search_query=search_query,
                catalog_empty=True,
            )

        if reply and not fallback and not _is_unusable_vodchat_reply(reply):
            return ChatResponse(
                reply=reply,
                fallback=False,
                videos=[],
                search_query=search_query,
                catalog_empty=False,
            )

        return ChatResponse(
            reply=FALLBACK_REPLY,
            fallback=True,
            videos=[],
            search_query=search_query,
            catalog_empty=False,
        )


def _filter_scored_videos(
    scored: list[tuple[Video, float]],
    keywords: list[str],
    limit: int,
) -> list[Video]:
    if not scored:
        return []

    if settings.CHAT_REQUIRE_TOPIC_KEYWORD_MATCH and keywords:
        matched = [
            video
            for video, _distance in scored
            if video_matches_topic(video.title, video.description, keywords)
        ]
        if matched:
            return matched[:limit]
        # Sem match no catalogo para o tema — nao devolver vizinhos aleatorios do embedding.
        return []

    return [video for video, _distance in scored[:limit]]


def _is_unusable_vodchat_reply(text: str) -> bool:
    """Texto do LLM que nao deve ir para o usuario (URL, lixo, muito curto)."""
    stripped = text.strip()
    if len(stripped) < 20:
        return True
    if _URL_PATTERN.search(stripped):
        return True
    if "Historico recente do usuario" in stripped:
        return True
    if "um titulo do catalogo" in stripped.lower():
        return True
    if _ENGLISH_HINTS.search(stripped):
        return True
    return False


def _out_of_catalog_reply(search_query: str) -> str:
    topic = " ".join(topic_keywords(search_query)) or search_query
    categorias = ", ".join(CATALOG_CATEGORIES)
    return (
        f"Não trabalhamos com \"{topic}\" — nosso acervo é de vídeos educativos "
        "e culturais brasileiros, não de filmes por gênero.\n\n"
        f"As categorias disponíveis são: {categorias}.\n\n"
        "Tente pedir, por exemplo: \"vídeos de natureza\", \"receitas de culinária\" "
        "ou \"tutoriais de tecnologia\"."
    )


def _empty_catalog_reply(search_query: str) -> str:
    topic = " ".join(topic_keywords(search_query)) or search_query
    return (
        f"Não encontrei vídeos sobre \"{topic}\" no catálogo.\n\n"
        "O catálogo atual não tem títulos com esse tema. Você pode:\n"
        "• Reformular o pedido (ex.: documentário, receitas, natureza)\n"
        "• Abrir Explorar e buscar com outras palavras\n"
        "• Ver a home — as recomendações usam seu histórico de visualização"
    )


def _catalog_reply(
    videos: list[ChatVideoSuggestion],
    search_query: str | None,
) -> str:
    topic = topic_keywords(search_query or "")
    topic_label = " ".join(topic) if topic else "que voce pediu"
    lines = [f"Separei estes vídeos sobre {topic_label}:"]
    for index, video in enumerate(videos, start=1):
        lines.append(f"{index}. {video.title}")
    return "\n".join(lines)


def _recommendation_reply(
    videos: list[ChatVideoSuggestion],
    message: str | None = None,
) -> str:
    normalized = _normalize_recommendation_context(message or "")
    if "namorad" in normalized or "casal" in normalized:
        header = "Separei sugestões para assistir a dois:"
    elif "familia" in normalized or "filhos" in normalized or "crianc" in normalized:
        header = "Separei sugestões para ver em família:"
    elif "amig" in normalized:
        header = "Separei sugestões para ver com amigos:"
    else:
        header = "Separei sugestões para você assistir hoje:"
    lines = [header]
    for index, video in enumerate(videos, start=1):
        lines.append(f"{index}. {video.title}")
    return "\n".join(lines)


def _normalize_recommendation_context(message: str) -> str:
    import unicodedata

    lowered = message.strip().lower()
    normalized = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def _video_to_suggestion(video: Video) -> ChatVideoSuggestion:
    return ChatVideoSuggestion.model_validate(video)
