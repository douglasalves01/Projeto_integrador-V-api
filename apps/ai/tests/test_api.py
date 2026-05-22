"""API integration tests with FastAPI TestClient and SQLite in-memory."""

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.schemas_db import UserProfileAI

settings = get_settings()


class TestRecommendationsAPI:
    def test_get_recommendations_returns_200_and_schema(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        response = test_client.get(
            f"{settings.API_PREFIX}/recommendations/1?k=10",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1
        assert "strategy" in data
        assert "model_version" in data
        assert "total_views" in data
        assert "generated_at" in data
        assert isinstance(data["recommendations"], list)
        if data["recommendations"]:
            item = data["recommendations"][0]
            assert "content_id" in item
            assert "score" in item
            assert "reason" in item

    def test_get_recommendations_cache_hit_is_faster(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        mock_redis_cache: dict,
    ) -> None:
        url = f"{settings.API_PREFIX}/recommendations/1?k=5"

        start_miss = time.perf_counter()
        first = test_client.get(url, headers=auth_headers)
        miss_elapsed = time.perf_counter() - start_miss

        assert first.status_code == 200
        cache_key = "recs:1:k5"
        assert cache_key in mock_redis_cache

        start_hit = time.perf_counter()
        second = test_client.get(url, headers=auth_headers)
        hit_elapsed = time.perf_counter() - start_hit

        assert second.status_code == 200
        assert second.json()["strategy"] == first.json()["strategy"]
        assert hit_elapsed < miss_elapsed

    def test_get_recommendations_forbidden_for_other_user(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        response = test_client.get(
            f"{settings.API_PREFIX}/recommendations/999",
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestProfileAPI:
    def test_post_profile_update_updates_profile(
        self,
        test_client: TestClient,
        auth_headers: dict[str, str],
        seeded_db,
    ) -> None:
        profile_before = seeded_db.query(UserProfileAI).filter(UserProfileAI.user_id == 1).one()
        views_before = profile_before.total_views

        response = test_client.post(
            f"{settings.API_PREFIX}/profile/1/update",
            headers=auth_headers,
            json={
                "content_id": 4,
                "watched_sec": 900,
                "total_sec": 3600,
                "ended_at": "2026-05-22T12:00:00Z",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1
        assert data["total_views"] == views_before + 1
        assert isinstance(data.get("genre_weights"), dict)

        seeded_db.expire_all()
        profile_after = seeded_db.query(UserProfileAI).filter(UserProfileAI.user_id == 1).one()
        assert profile_after.total_views == views_before + 1


class TestHealthAPI:
    def test_health_returns_200(self, test_client: TestClient) -> None:
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in {"healthy", "degraded"}
        assert "mysql" in data
        assert "redis" in data
        assert "models_loaded" in data

    def test_api_v1_health_returns_200(self, test_client: TestClient) -> None:
        response = test_client.get(f"{settings.API_PREFIX}/health")
        assert response.status_code == 200
