"""E2E tests for authentication and registration flows."""
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRegistration:
    async def test_register_success(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "New User",
                "email": "newuser@example.com",
                "password": "securepass123",
                "plan_id": str(seed_data["plans"][0]["id"]),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New User"
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "USER"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data

    async def test_register_duplicate_email(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "Another",
                "email": seed_data["user"]["email"],
                "password": "securepass123",
                "plan_id": str(seed_data["plans"][0]["id"]),
            },
        )
        assert response.status_code == 409

    async def test_register_invalid_email(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "User",
                "email": "not-an-email",
                "password": "securepass123",
                "plan_id": str(seed_data["plans"][0]["id"]),
            },
        )
        assert response.status_code == 422

    async def test_register_short_password(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "User",
                "email": "short@example.com",
                "password": "short",
                "plan_id": str(seed_data["plans"][0]["id"]),
            },
        )
        assert response.status_code == 422

    async def test_register_long_password(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "User",
                "email": "long@example.com",
                "password": "a" * 129,
                "plan_id": str(seed_data["plans"][0]["id"]),
            },
        )
        assert response.status_code == 422

    async def test_register_empty_name(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "",
                "email": "empty@example.com",
                "password": "securepass123",
                "plan_id": str(seed_data["plans"][0]["id"]),
            },
        )
        assert response.status_code == 422

    async def test_register_name_too_long(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "A" * 101,
                "email": "toolong@example.com",
                "password": "securepass123",
                "plan_id": str(seed_data["plans"][0]["id"]),
            },
        )
        assert response.status_code == 422

    async def test_register_invalid_plan(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/register",
            json={
                "name": "User",
                "email": "badplan@example.com",
                "password": "securepass123",
                "plan_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 422

    async def test_register_missing_fields(self, client: AsyncClient, seed_data):
        response = await client.post("/auth/register", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestLogin:
    async def test_login_success(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/login",
            json={"email": seed_data["user"]["email"], "password": seed_data["user"]["password"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/login",
            json={"email": seed_data["user"]["email"], "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    async def test_login_nonexistent_email(self, client: AsyncClient, seed_data):
        response = await client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "somepass123"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    async def test_login_same_error_message(self, client: AsyncClient, seed_data):
        """Both wrong email and wrong password return the same generic message."""
        resp1 = await client.post("/auth/login", json={"email": "wrong@x.com", "password": "x"})
        resp2 = await client.post("/auth/login", json={"email": seed_data["user"]["email"], "password": "wrong"})
        assert resp1.json()["detail"] == resp2.json()["detail"]

    async def test_login_missing_fields(self, client: AsyncClient, seed_data):
        response = await client.post("/auth/login", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestRefreshToken:
    async def test_refresh_success(self, client: AsyncClient, seed_data):
        login_resp = await client.post(
            "/auth/login",
            json={"email": seed_data["user"]["email"], "password": seed_data["user"]["password"]},
        )
        refresh_token = login_resp.json()["refresh_token"]

        response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["refresh_token"] != refresh_token

    async def test_refresh_token_single_use(self, client: AsyncClient, seed_data):
        login_resp = await client.post(
            "/auth/login",
            json={"email": seed_data["admin"]["email"], "password": seed_data["admin"]["password"]},
        )
        refresh_token = login_resp.json()["refresh_token"]

        resp1 = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp1.status_code == 200

        resp2 = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp2.status_code == 401

    async def test_refresh_invalid_token(self, client: AsyncClient, seed_data):
        response = await client.post("/auth/refresh", json={"refresh_token": "invalid.token"})
        assert response.status_code == 401

    async def test_refresh_with_access_token(self, client: AsyncClient, seed_data):
        login_resp = await client.post(
            "/auth/login",
            json={"email": seed_data["user"]["email"], "password": seed_data["user"]["password"]},
        )
        access_token = login_resp.json()["access_token"]
        response = await client.post("/auth/refresh", json={"refresh_token": access_token})
        assert response.status_code == 401
