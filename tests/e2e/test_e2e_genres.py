"""E2E tests for genre CRUD."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestGenreCRUD:
    async def test_admin_creates_genre(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/genres", json={"name": "Horror"})
        assert response.status_code == 201
        assert response.json()["name"] == "Horror"

    async def test_create_duplicate_genre(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/genres", json={"name": seed_data["genres"][0]["name"]})
        assert response.status_code == 409

    async def test_user_cannot_create_genre(self, user_client: AsyncClient, seed_data):
        response = await user_client.post("/genres", json={"name": "Mystery"})
        assert response.status_code == 403

    async def test_create_genre_empty_name(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/genres", json={"name": ""})
        assert response.status_code == 422

    async def test_list_genres(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/genres")
        assert response.status_code == 200
        assert response.json()["total"] >= 4

    async def test_update_genre(self, admin_client: AsyncClient, seed_data):
        # Create one to update
        resp = await admin_client.post("/genres", json={"name": "ToUpdate"})
        gid = resp.json()["id"]
        response = await admin_client.put(f"/genres/{gid}", json={"name": "Updated"})
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    async def test_update_nonexistent_genre(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.put(f"/genres/{uuid.uuid4()}", json={"name": "X"})
        assert response.status_code == 404

    async def test_delete_genre_not_in_use(self, admin_client: AsyncClient, seed_data):
        resp = await admin_client.post("/genres", json={"name": "Deletable"})
        gid = resp.json()["id"]
        response = await admin_client.delete(f"/genres/{gid}")
        assert response.status_code == 204

    async def test_delete_genre_in_use(self, admin_client: AsyncClient, seed_data):
        gid = str(seed_data["genres"][0]["id"])
        response = await admin_client.delete(f"/genres/{gid}")
        assert response.status_code == 409

    async def test_delete_nonexistent_genre(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.delete(f"/genres/{uuid.uuid4()}")
        assert response.status_code == 404
