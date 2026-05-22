"""E2E tests for favorites."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestFavorites:
    async def test_add_favorite(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][0]["id"])
        response = await user_client.post(f"/favorites/{vid}")
        assert response.status_code == 201
        assert response.json()["video_id"] == vid

    async def test_add_favorite_duplicate(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][1]["id"])
        await user_client.post(f"/favorites/{vid}")
        response = await user_client.post(f"/favorites/{vid}")
        assert response.status_code == 409

    async def test_add_favorite_nonexistent_video(self, user_client: AsyncClient, seed_data):
        response = await user_client.post(f"/favorites/{uuid.uuid4()}")
        assert response.status_code == 404

    async def test_remove_favorite(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][2]["id"])
        await user_client.post(f"/favorites/{vid}")
        response = await user_client.delete(f"/favorites/{vid}")
        assert response.status_code == 204

    async def test_remove_favorite_not_found(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][3]["id"])
        response = await user_client.delete(f"/favorites/{vid}")
        assert response.status_code == 404

    async def test_list_favorites(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/favorites")
        assert response.status_code == 200
        assert "items" in response.json()
