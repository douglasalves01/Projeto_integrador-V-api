import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.video import Video
from app.schemas.chat import ChatVideoSuggestion
from app.services.chat_intent import (
    expand_topic_keywords,
    extract_search_query,
    is_greeting_only,
    should_attach_videos,
    topic_keywords,
    video_matches_topic,
)
from app.services.chat_service import ChatService, _filter_scored_videos, _is_unusable_vodchat_reply


def test_should_attach_videos_culinaria():
    assert should_attach_videos("quero videos de culinaria") is True


def test_should_not_attach_greeting():
    assert should_attach_videos("oi") is False
    assert is_greeting_only("oi") is True


def test_extract_search_query_strips_prefix():
    assert extract_search_query("me mostre videos de culinaria") == "culinaria"
    assert extract_search_query("quero videos de culinaria") == "culinaria"
    assert extract_search_query("quero videos de natureza") == "natureza"
    assert extract_search_query("quero assistir videos de culinaria") == "culinaria"
    assert extract_search_query("me recomende videos que falem sobre policia") == "policia"
    assert extract_search_query("me recomende videos policiais") == "policiais"


def test_empty_catalog_reply_message():
    from app.services.chat_service import _empty_catalog_reply

    text = _empty_catalog_reply("policiais")
    assert "Não encontrei vídeos" in text
    assert "policiais" in text
    assert "Explorar" in text


def test_build_response_empty_catalog_ignores_vodchat():
    from app.services.chat_service import ChatService

    service = ChatService()
    response = service._build_response(
        reply="Texto longo inventado pelo modelo sobre policia portuguesa...",
        fallback=False,
        videos=[],
        search_query="policiais",
    )
    assert response.catalog_empty is True
    assert response.videos == []
    assert "Não encontrei vídeos" in response.reply
    assert "portuguesa" not in response.reply.lower()


def test_topic_keywords_natureza():
    assert topic_keywords("natureza") == ["natureza"]


def test_expand_topic_keywords_includes_amazonia():
    expanded = expand_topic_keywords("natureza")
    assert "amazonia" in expanded
    assert "floresta" in expanded


def test_video_matches_topic_natureza_synonyms():
    keywords = expand_topic_keywords("natureza")
    assert video_matches_topic(
        "AMAZONIA SELVAGEM DOCUMENTARIO",
        "animais selvagens da floresta amazonica",
        keywords,
    )
    assert not video_matches_topic(
        "COMO FAZER VELAS AROMATICAS",
        "cera e essencia",
        keywords,
    )


def test_filter_scored_videos_empty_when_no_keyword_match():
    v1 = Video(
        id=uuid.uuid4(),
        title="Velas aromaticas",
        description="artesanato",
        url="/v1",
        duration_seconds=100,
    )
    assert _filter_scored_videos([(v1, 0.2)], ["policia"], limit=5) == []


def test_filter_scored_videos_prefers_keyword_match():
    v1 = Video(
        id=uuid.uuid4(),
        title="Documentario Amazonia",
        description="natureza selvagem",
        url="/v1",
        duration_seconds=100,
    )
    v2 = Video(
        id=uuid.uuid4(),
        title="Velas aromaticas",
        description="artesanato",
        url="/v2",
        duration_seconds=100,
    )
    filtered = _filter_scored_videos([(v2, 0.3), (v1, 0.4)], ["natureza"], limit=5)
    assert len(filtered) == 1
    assert filtered[0].title.startswith("Documentario")


def test_unusable_vodchat_detects_urls():
    assert _is_unusable_vodchat_reply("Veja https://youtube.com/watch?v=abc")


def test_unusable_vodchat_detects_english_and_placeholder():
    assert _is_unusable_vodchat_reply("Sure, I can provide you with some recommendations")
    assert _is_unusable_vodchat_reply('Veja "um titulo do catalogo" no catalogo')


@pytest.mark.asyncio
async def test_chat_returns_videos_when_search_finds_results(auth_client: AsyncClient):
    video_id = uuid.uuid4()
    suggestion = ChatVideoSuggestion(
        id=video_id,
        title="Cozinha em 30 min",
        description="Receitas rapidas",
        url="https://example.com/v1.mp4",
        duration_seconds=1800,
    )

    with (
        patch(
            "app.services.chat_service.ChatService._fetch_vodchat_reply",
            new_callable=AsyncMock,
            return_value=(None, True),
        ),
        patch(
            "app.services.chat_service.ChatService._fetch_video_suggestions",
            new_callable=AsyncMock,
            return_value=[suggestion],
        ),
    ):
        response = await auth_client.post(
            "/chat",
            json={"message": "quero videos de culinaria"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["fallback"] is True
    assert len(data["videos"]) == 1
    assert data["videos"][0]["title"] == "Cozinha em 30 min"
    assert data["search_query"] is not None
    assert "Separei estes v" in data["reply"]


@pytest.mark.asyncio
async def test_chat_vodchat_reply_with_videos(auth_client: AsyncClient):
    video_id = uuid.uuid4()
    suggestion = ChatVideoSuggestion(
        id=video_id,
        title="Natureza Selvagem",
        description=None,
        url="https://example.com/v2.mp4",
        duration_seconds=3600,
    )

    with (
        patch(
            "app.services.chat_service.ChatService._fetch_vodchat_reply",
            new_callable=AsyncMock,
            return_value=("Aqui estao algumas ideias.", False),
        ),
        patch(
            "app.services.chat_service.ChatService._fetch_video_suggestions",
            new_callable=AsyncMock,
            return_value=[suggestion],
        ),
    ):
        response = await auth_client.post(
            "/chat",
            json={"message": "documentarios de natureza"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["fallback"] is False
    assert "Natureza Selvagem" in data["reply"]
    assert len(data["videos"]) == 1


@pytest.mark.asyncio
async def test_chat_greeting_no_videos(auth_client: AsyncClient):
    with patch(
        "app.services.chat_service.ChatService._fetch_vodchat_reply",
        new_callable=AsyncMock,
        return_value=("Ola! Como posso ajudar?", False),
    ):
        response = await auth_client.post("/chat", json={"message": "oi"})

    assert response.status_code == 200
    data = response.json()
    assert data["videos"] == []
    assert data.get("search_query") in (None, "")


@pytest.mark.asyncio
async def test_chat_replaces_garbage_vodchat_with_catalog_list(auth_client: AsyncClient):
    video_id = uuid.uuid4()
    suggestion = ChatVideoSuggestion(
        id=video_id,
        title="Floresta Amazonica",
        description="natureza",
        url="https://example.com/v.mp4",
        duration_seconds=600,
    )
    with (
        patch(
            "app.services.chat_service.ChatService._fetch_vodchat_reply",
            new_callable=AsyncMock,
            return_value=("Links: https://youtube.com/watch?v=abc", False),
        ),
        patch(
            "app.services.chat_service.ChatService._fetch_video_suggestions",
            new_callable=AsyncMock,
            return_value=[suggestion],
        ),
    ):
        response = await auth_client.post(
            "/chat",
            json={"message": "quero videos de natureza"},
        )
    data = response.json()
    assert "Floresta Amazonica" in data["reply"]
    assert "youtube.com" not in data["reply"]


@pytest.mark.asyncio
async def test_fetch_culinaria_uses_keyword_fallback(db_session):
    brigadeiro = Video(
        id=uuid.uuid4(),
        title="COMO FAZER BRIGADEIRO",
        description="receita de brigadeiro com leite condensado",
        url="/videos/brigadeiro/stream",
        duration_seconds=120,
    )
    velas = Video(
        id=uuid.uuid4(),
        title="VELAS AROMATICAS",
        description="artesanato com cera",
        url="/videos/velas/stream",
        duration_seconds=200,
    )
    db_session.add_all([brigadeiro, velas])
    await db_session.flush()

    service = ChatService()
    with patch.object(
        service,
        "_semantic_chat_search",
        new_callable=AsyncMock,
        return_value=[],
    ):
        # semantic mock empty — keyword path must still find brigadeiro
        pass

    # Call real semantic path (no mock on _fetch) — patch only scored to empty
    with (
        patch.object(
            service.video_service,
            "search_videos_semantic_scored",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        suggestions = await service._fetch_video_suggestions(db_session, "culinaria")

    assert len(suggestions) >= 1
    assert any("BRIGADEIRO" in s.title for s in suggestions)


@pytest.mark.asyncio
async def test_chat_service_maps_video_model(db_session):
    video = Video(
        id=uuid.uuid4(),
        title="Test Video",
        description="Desc",
        url="https://example.com/v.mp4",
        duration_seconds=120,
    )
    db_session.add(video)
    await db_session.flush()

    service = ChatService()
    with patch.object(
        service.video_service,
        "search_videos_semantic_scored",
        new_callable=AsyncMock,
        return_value=[(video, 0.2)],
    ):
        suggestions = await service._fetch_video_suggestions(db_session, "test")

    assert len(suggestions) == 1
    assert suggestions[0].title == "Test Video"
