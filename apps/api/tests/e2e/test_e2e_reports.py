"""E2E tests for admin reports."""
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestReports:
    async def test_usage_report(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/reports/usage")
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "active_users" in data
        assert "total_watch_sessions" in data
        assert "average_watch_time_seconds" in data

    async def test_usage_report_with_date_range(self, admin_client: AsyncClient, seed_data):
        start = (datetime.utcnow() - timedelta(days=1)).isoformat()
        end = (datetime.utcnow() + timedelta(days=1)).isoformat()
        response = await admin_client.get("/admin/reports/usage", params={"start_date": start, "end_date": end})
        assert response.status_code == 200

    async def test_usage_report_invalid_date_range(self, admin_client: AsyncClient, seed_data):
        start = (datetime.utcnow() + timedelta(days=1)).isoformat()
        end = (datetime.utcnow() - timedelta(days=1)).isoformat()
        response = await admin_client.get("/admin/reports/usage", params={"start_date": start, "end_date": end})
        assert response.status_code == 422

    async def test_most_watched(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/reports/most-watched")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_abandonment(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/reports/abandonment")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_popular_genres(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/reports/popular-genres")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_active_users(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.get("/admin/reports/active-users")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_user_cannot_access_reports(self, user_client: AsyncClient, seed_data):
        endpoints = [
            "/admin/reports/usage",
            "/admin/reports/most-watched",
            "/admin/reports/abandonment",
            "/admin/reports/popular-genres",
            "/admin/reports/active-users",
        ]
        for endpoint in endpoints:
            response = await user_client.get(endpoint)
            assert response.status_code == 403, f"Expected 403 for {endpoint}"

    async def test_most_watched_invalid_range(self, admin_client: AsyncClient, seed_data):
        start = (datetime.utcnow() + timedelta(days=1)).isoformat()
        end = (datetime.utcnow() - timedelta(days=1)).isoformat()
        response = await admin_client.get("/admin/reports/most-watched", params={"start_date": start, "end_date": end})
        assert response.status_code == 422
