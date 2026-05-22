"""E2E tests for category CRUD."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestCategoryCRUD:
    async def test_admin_creates_category(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/categories", json={"name": "Animation"})
        assert response.status_code == 201

    async def test_create_duplicate_category(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/categories", json={"name": seed_data["categories"][0]["name"]})
        assert response.status_code == 409

    async def test_user_cannot_create_category(self, user_client: AsyncClient, seed_data):
        response = await user_client.post("/categories", json={"name": "Podcast"})
        assert response.status_code == 403

    async def test_list_categories(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/categories")
        assert response.status_code == 200
        assert response.json()["total"] >= 4

    async def test_delete_category_in_use(self, admin_client: AsyncClient, seed_data):
        cid = str(seed_data["categories"][0]["id"])
        response = await admin_client.delete(f"/categories/{cid}")
        assert response.status_code == 409

    async def test_delete_category_not_in_use(self, admin_client: AsyncClient, seed_data):
        resp = await admin_client.post("/categories", json={"name": "Temp"})
        cid = resp.json()["id"]
        response = await admin_client.delete(f"/categories/{cid}")
        assert response.status_code == 204
