"""E2E tests for watch sessions."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestWatchSessions:
    async def test_watch_creates_session(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][0]["id"])
        await user_client.get(f"/videos/{vid}/watch")

        response = await user_client.get("/watch-history")
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    async def test_update_watch_session_half(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][4]["id"])  # 1800s
        await user_client.get(f"/videos/{vid}/watch")

        history = await user_client.get("/watch-history")
        items = history.json()["items"]
        session_id = items[0]["id"]

        response = await user_client.patch(
            f"/watch-sessions/{session_id}",
            json={"watch_time_seconds": 900},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["watch_time_seconds"] == 900
        assert data["percentage_watched"] == pytest.approx(0.5, abs=0.01)
        assert data["completed"] is False
        assert data["abandoned"] is False

    async def test_update_watch_session_completed(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][4]["id"])  # 1800s
        await user_client.get(f"/videos/{vid}/watch")

        history = await user_client.get("/watch-history")
        session_id = history.json()["items"][0]["id"]

        response = await user_client.patch(
            f"/watch-sessions/{session_id}",
            json={"watch_time_seconds": 1700},
        )
        assert response.status_code == 200
        assert response.json()["completed"] is True

    async def test_update_watch_session_abandoned(self, user_client: AsyncClient, seed_data):
        vid = str(seed_data["videos"][2]["id"])  # 7200s
        await user_client.get(f"/videos/{vid}/watch")

        history = await user_client.get("/watch-history")
        session_id = history.json()["items"][0]["id"]

        response = await user_client.patch(
            f"/watch-sessions/{session_id}",
            json={"watch_time_seconds": 50},
        )
        assert response.status_code == 200
        assert response.json()["abandoned"] is True

    async def test_update_nonexistent_session(self, user_client: AsyncClient, seed_data):
        response = await user_client.patch(
            f"/watch-sessions/{uuid.uuid4()}",
            json={"watch_time_seconds": 100},
        )
        assert response.status_code == 404

    async def test_watch_history_no_auth(self, client: AsyncClient, seed_data):
        response = await client.get("/watch-history")
        assert response.status_code == 403
