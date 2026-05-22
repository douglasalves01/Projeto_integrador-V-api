"""API tests for /llm endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from uuid import UUID

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from tests.conftest import OTHER_USER_UUID, TEST_USER_UUID

settings = get_settings()


@pytest.fixture
def api_client(llm_test_client: TestClient) -> TestClient:
    return llm_test_client


@pytest.fixture
def llm_client_no_auth_override(seeded_db) -> TestClient:
    """TestClient without JWT override — enforces real auth on LLM routes."""

    def _override_db():
        yield seeded_db

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestLLMRoutes:
    def test_recommendations_requires_auth(self, llm_client_no_auth_override: TestClient) -> None:
        response = llm_client_no_auth_override.get(
            f"{settings.API_PREFIX}/llm/recommendations/{TEST_USER_UUID}?k=5",
        )
        assert response.status_code in {401, 403}

    def test_recommendations_forbidden_for_other_user(
        self,
        api_client: TestClient,
        llm_auth_headers: dict[str, str],
    ) -> None:
        response = api_client.get(
            f"{settings.API_PREFIX}/llm/recommendations/{OTHER_USER_UUID}?k=5",
            headers=llm_auth_headers,
        )
        assert response.status_code == 403

    def test_chat_requires_auth(self, llm_client_no_auth_override: TestClient) -> None:
        response = llm_client_no_auth_override.post(
            f"{settings.API_PREFIX}/llm/chat/{TEST_USER_UUID}",
            json={"message": "oi"},
        )
        assert response.status_code in {401, 403}

    def test_info_returns_200_when_not_loaded(self, api_client: TestClient) -> None:
        with patch(
            "app.api.routes.llm.svc.get_model_info",
            return_value={"loaded": False, "vodrec": None, "vodchat": {"loaded": False}},
        ):
            response = api_client.get(f"{settings.API_PREFIX}/llm/info")
        assert response.status_code == 200
        assert response.json()["loaded"] is False

    def test_recommendations_empty_history(
        self,
        api_client: TestClient,
        llm_auth_headers: dict[str, str],
    ) -> None:
        with (
            patch("app.api.routes.llm.svc.get_model_info", return_value={"loaded": True}),
            patch("app.api.routes.llm._load_user_history", return_value=[]),
            patch(
                "app.api.routes.llm.svc.get_recommendations",
                return_value={
                    "model_version": "vodrec-v1.0",
                    "strategy": "empty_history",
                    "total_views": 0,
                    "recommendations": [],
                    "top_explanation": None,
                },
            ),
        ):
            response = api_client.get(
                f"{settings.API_PREFIX}/llm/recommendations/{TEST_USER_UUID}?k=5",
                headers=llm_auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total_views"] == 0
        assert data["recommendations"] == []

    def test_chat_returns_503_without_vodchat(
        self,
        api_client: TestClient,
        llm_auth_headers: dict[str, str],
    ) -> None:
        with patch(
            "app.api.routes.llm.svc.get_model_info",
            return_value={"loaded": False},
        ):
            response = api_client.post(
                f"{settings.API_PREFIX}/llm/chat/{TEST_USER_UUID}",
                headers=llm_auth_headers,
                json={"message": "recomende algo"},
            )
        assert response.status_code == 503

    def test_recommendations_with_mock_orchestrator(
        self,
        api_client: TestClient,
        llm_auth_headers: dict[str, str],
    ) -> None:
        mock_result = {
            "model_version": "vodrec-v1.0",
            "strategy": "llm_hybrid",
            "total_views": 3,
            "recommendations": [{"content_id": 4, "score": 0.8, "title": "T", "genres": [], "reason": None}],
            "top_explanation": None,
        }
        with (
            patch("app.api.routes.llm.svc.get_model_info", return_value={"loaded": True}),
            patch("app.api.routes.llm._load_user_history", return_value=[]),
            patch("app.api.routes.llm.svc.get_recommendations", return_value=mock_result),
        ):
            response = api_client.get(
                f"{settings.API_PREFIX}/llm/recommendations/{TEST_USER_UUID}?k=5",
                headers=llm_auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["content_id"] == str(UUID(int=4))
