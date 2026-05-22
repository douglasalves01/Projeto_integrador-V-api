"""E2E tests for interaction logging."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestInteractions:
    async def test_watch_logs_click(self, admin_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][0]["id"])
        await admin_client.get(f"/videos/{vid}/watch")

        response = await admin_client.get("/admin/interactions")
        assert response.status_code == 200
        items = response.json()["items"]
        click_logs = [i for i in items if i["interaction_type"] == "CLICK"]
        assert len(click_logs) >= 1

    async def test_search_logs_search(self, admin_client: AsyncClient, seed_data):
        await admin_client.get("/videos/search", params={"q": "future"})

        response = await admin_client.get("/admin/interactions")
        assert response.status_code == 200
        items = response.json()["items"]
        search_logs = [i for i in items if i["interaction_type"] == "SEARCH"]
        assert len(search_logs) >= 1

    async def test_favorite_logs_interaction(self, admin_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][3]["id"])
        await admin_client.post(f"/favorites/{vid}")

        response = await admin_client.get("/admin/interactions")
        items = response.json()["items"]
        fav_logs = [i for i in items if i["interaction_type"] == "FAVORITE"]
        assert len(fav_logs) >= 1

    async def test_filter_by_type(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/interactions", params={"interaction_type": "CLICK"})
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["interaction_type"] == "CLICK"

    async def test_user_cannot_list_interactions(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/admin/interactions")
        assert response.status_code == 403

    async def test_interactions_pagination(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/interactions", params={"page": 1, "page_size": 2})
        assert response.status_code == 200
        assert len(response.json()["items"]) <= 2
