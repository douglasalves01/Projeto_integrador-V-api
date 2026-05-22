"""E2E tests for role-based access control."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRBAC:
    """USER cannot access ADMIN-only endpoints."""

    async def test_user_cannot_create_genre(self, user_client, seed_data):
        assert (await user_client.post("/genres", json={"name": "X"})).status_code == 403

    async def test_user_cannot_create_category(self, user_client, seed_data):
        assert (await user_client.post("/categories", json={"name": "X"})).status_code == 403

    async def test_user_cannot_create_plan(self, user_client, seed_data):
        assert (await user_client.post("/plans", json={"name": "X"})).status_code == 403

    async def test_user_cannot_create_video(self, user_client, seed_data):
        assert (await user_client.post("/videos", json={
            "title": "X", "url": "https://x.com/x.mp4", "duration_seconds": 60,
            "genre_ids": [str(seed_data["genres"][0]["id"])],
            "category_ids": [str(seed_data["categories"][0]["id"])],
        })).status_code == 403

    async def test_user_cannot_list_users(self, user_client, seed_data):
        assert (await user_client.get("/users")).status_code == 403

    async def test_user_cannot_access_admin_interactions(self, user_client, seed_data):
        assert (await user_client.get("/admin/interactions")).status_code == 403

    async def test_user_cannot_access_admin_recommendations(self, user_client, seed_data):
        assert (await user_client.get("/admin/recommendations")).status_code == 403

    async def test_user_cannot_access_reports(self, user_client, seed_data):
        assert (await user_client.get("/admin/reports/usage")).status_code == 403

    async def test_unauthenticated_rejected(self, client, seed_data):
        assert (await client.get("/users/me")).status_code == 403
        assert (await client.get("/videos")).status_code == 403
        assert (await client.get("/recommendations")).status_code == 403

    async def test_invalid_token_rejected(self, client, seed_data):
        client.headers["Authorization"] = "Bearer invalid.token"
        assert (await client.get("/users/me")).status_code == 401

    async def test_admin_can_access_user_endpoints(self, admin_client, seed_data):
        assert (await admin_client.get("/users/me")).status_code == 200
        assert (await admin_client.get("/videos")).status_code == 200
        assert (await admin_client.get("/recommendations")).status_code == 200
