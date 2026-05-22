"""E2E tests for video CRUD and discovery."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestVideoCRUD:
    async def test_admin_creates_video(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/videos", json={
            "title": "New Video",
            "description": "Desc",
            "url": "https://example.com/new.mp4",
            "duration_seconds": 3600,
            "genre_ids": [str(seed_data["genres"][0]["id"])],
            "category_ids": [str(seed_data["categories"][0]["id"])],
        })
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Video"
        assert len(data["genres"]) == 1
        assert len(data["categories"]) == 1

    async def test_create_video_invalid_genre(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/videos", json={
            "title": "Bad", "url": "https://x.com/x.mp4", "duration_seconds": 100,
            "genre_ids": [str(uuid.uuid4())],
            "category_ids": [str(seed_data["categories"][0]["id"])],
        })
        assert response.status_code == 422

    async def test_create_video_no_genres(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/videos", json={
            "title": "No Genre", "url": "https://x.com/x.mp4", "duration_seconds": 100,
            "genre_ids": [],
            "category_ids": [str(seed_data["categories"][0]["id"])],
        })
        assert response.status_code == 422

    async def test_create_video_duration_zero(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/videos", json={
            "title": "Zero", "url": "https://x.com/x.mp4", "duration_seconds": 0,
            "genre_ids": [str(seed_data["genres"][0]["id"])],
            "category_ids": [str(seed_data["categories"][0]["id"])],
        })
        assert response.status_code == 422

    async def test_user_cannot_create_video(self, user_client: AsyncClient, seed_data):
        response = await user_client.post("/videos", json={
            "title": "X", "url": "https://x.com/x.mp4", "duration_seconds": 100,
            "genre_ids": [str(seed_data["genres"][0]["id"])],
            "category_ids": [str(seed_data["categories"][0]["id"])],
        })
        assert response.status_code == 403

    async def test_list_videos(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/videos")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5

    async def test_list_videos_pagination(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/videos", params={"page": 1, "page_size": 2})
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2

    async def test_search_by_title(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/videos/search", params={"q": "future"})
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    async def test_search_by_genre(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/videos/search", params={"genre_id": str(seed_data["genres"][0]["id"])})
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    async def test_search_by_category(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/videos/search", params={"category_id": str(seed_data["categories"][0]["id"])})
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    async def test_search_no_results(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/videos/search", params={"q": "xyznonexistent"})
        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_update_video(self, admin_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][0]["id"])
        response = await admin_client.put(f"/videos/{vid}", json={"title": "Updated Title"})
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    async def test_delete_video(self, admin_client: AsyncClient, seed_data):
        # Create one to delete
        resp = await admin_client.post("/videos", json={
            "title": "ToDelete", "url": "https://x.com/del.mp4", "duration_seconds": 60,
            "genre_ids": [str(seed_data["genres"][0]["id"])],
            "category_ids": [str(seed_data["categories"][0]["id"])],
        })
        vid = resp.json()["id"]
        response = await admin_client.delete(f"/videos/{vid}")
        assert response.status_code == 204

    async def test_watch_video(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][0]["id"])
        response = await user_client.get(f"/videos/{vid}/watch")
        assert response.status_code == 200
        assert response.json()["url"] is not None

    async def test_watch_nonexistent_video(self, user_client: AsyncClient, seed_data):
        response = await user_client.get(f"/videos/{uuid.uuid4()}/watch")
        assert response.status_code == 404
