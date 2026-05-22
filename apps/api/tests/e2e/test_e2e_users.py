"""E2E tests for user profile and management."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestUserProfile:
    async def test_get_own_profile(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == seed_data["user"]["email"]
        assert data["role"] == "USER"
        assert "password_hash" not in data

    async def test_get_profile_no_auth(self, client: AsyncClient, seed_data):
        response = await client.get("/users/me")
        assert response.status_code == 403

    async def test_get_profile_invalid_token(self, client: AsyncClient, seed_data):
        client.headers["Authorization"] = "Bearer invalid.token.here"
        response = await client.get("/users/me")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUserList:
    async def test_admin_can_list_users(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/users")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert data["page_size"] == 20

    async def test_user_cannot_list_users(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/users")
        assert response.status_code == 403

    async def test_list_users_pagination(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/users", params={"page": 1, "page_size": 1})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total_pages"] >= 2

    async def test_list_users_max_page_size(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/users", params={"page_size": 200})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestUserDeactivation:
    async def test_admin_cannot_deactivate_self(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.patch(f"/users/{seed_data['admin']['id']}/deactivate")
        assert response.status_code == 403

    async def test_deactivate_nonexistent_user(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.patch(f"/users/{uuid.uuid4()}/deactivate")
        assert response.status_code == 404

    async def test_user_cannot_deactivate(self, user_client: AsyncClient, seed_data):
        response = await user_client.patch(f"/users/{seed_data['admin']['id']}/deactivate")
        assert response.status_code == 403
