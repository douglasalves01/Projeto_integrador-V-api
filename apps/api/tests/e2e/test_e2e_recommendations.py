"""E2E tests for recommendations."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRecommendations:
    async def test_get_recommendations(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    async def test_recommendations_ordered_by_score(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/recommendations")
        data = response.json()
        if len(data) >= 2:
            scores = [r["relevance_score"] for r in data]
            assert scores == sorted(scores, reverse=True)

    async def test_recommendations_have_explanation(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/recommendations")
        for rec in response.json():
            assert "explanation" in rec
            assert len(rec["explanation"]) > 0

    async def test_recommendations_no_auth(self, client: AsyncClient, seed_data):
        response = await client.get("/recommendations")
        assert response.status_code == 403

    async def test_admin_lists_all_recommendations(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/recommendations")
        assert response.status_code == 200
        assert "items" in response.json()

    async def test_user_cannot_access_admin_recommendations(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/admin/recommendations")
        assert response.status_code == 403
