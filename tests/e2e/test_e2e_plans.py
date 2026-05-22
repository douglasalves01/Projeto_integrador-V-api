"""E2E tests for plan CRUD."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPlanCRUD:
    async def test_admin_creates_plan(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/plans", json={"name": "Enterprise"})
        assert response.status_code == 201

    async def test_create_duplicate_plan(self, admin_client: AsyncClient, seed_data):
        response = await admin_client.post("/plans", json={"name": seed_data["plans"][0]["name"]})
        assert response.status_code == 409

    async def test_user_cannot_create_plan(self, user_client: AsyncClient, seed_data):
        response = await user_client.post("/plans", json={"name": "Free"})
        assert response.status_code == 403

    async def test_list_plans(self, user_client: AsyncClient, seed_data):
        response = await user_client.get("/plans")
        assert response.status_code == 200
        assert response.json()["total"] >= 3

    async def test_delete_plan_in_use(self, admin_client: AsyncClient, seed_data):
        pid = str(seed_data["plans"][0]["id"])
        response = await admin_client.delete(f"/plans/{pid}")
        assert response.status_code == 409

    async def test_delete_plan_not_in_use(self, admin_client: AsyncClient, seed_data):
        resp = await admin_client.post("/plans", json={"name": "TempPlan"})
        pid = resp.json()["id"]
        response = await admin_client.delete(f"/plans/{pid}")
        assert response.status_code == 204
