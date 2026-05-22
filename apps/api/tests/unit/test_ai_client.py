"""Unit tests for AI service HTTP client URL construction."""
from uuid import UUID

from app.integrations.ai_client import AIClient, normalize_ai_base_url


class TestNormalizeAiBaseUrl:
    def test_appends_api_v1_when_missing(self):
        assert normalize_ai_base_url("http://ai:8000") == "http://ai:8000/api/v1"

    def test_preserves_existing_api_v1(self):
        assert (
            normalize_ai_base_url("http://localhost:8002/api/v1")
            == "http://localhost:8002/api/v1"
        )

    def test_strips_trailing_slash_before_append(self):
        assert normalize_ai_base_url("http://ai:8000/") == "http://ai:8000/api/v1"


class TestAIClientUrls:
    def test_recommendations_url_uses_api_prefix(self):
        client = AIClient("http://ai:8000")
        user_id = UUID("00000000-0000-0000-0000-000000000001")
        url = f"{client.base_url}/llm/recommendations/{user_id}"
        assert url == (
            "http://ai:8000/api/v1/llm/recommendations/"
            "00000000-0000-0000-0000-000000000001"
        )
