import uuid

import pytest
from httpx import AsyncClient

from app.models.plan import Plan
from app.models.user import User


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient, test_plan: Plan):
    response = await client.post(
        "/auth/register",
        json={
            "name": "New User",
            "email": "newuser@example.com",
            "password": "securepass123",
            "plan_id": str(test_plan.id),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New User"
    assert data["email"] == "newuser@example.com"
    assert data["role"] == "USER"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_plan: Plan, test_user: User):
    response = await client.post(
        "/auth/register",
        json={
            "name": "Another User",
            "email": test_user.email,
            "password": "securepass123",
            "plan_id": str(test_plan.id),
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    response = await client.post(
        "/auth/login",
        json={
            "email": "testuser@example.com",
            "password": "testpassword123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient, test_user: User):
    response = await client.post(
        "/auth/login",
        json={
            "email": "testuser@example.com",
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_wrong_email(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "somepassword",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_get_profile(auth_client: AsyncClient, test_user: User):
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["name"] == test_user.name


@pytest.mark.asyncio
async def test_get_profile_unauthorized(client: AsyncClient):
    response = await client.get("/users/me")
    assert response.status_code == 403  # HTTPBearer returns 403 when no credentials


@pytest.mark.asyncio
async def test_register_invalid_password(client: AsyncClient, test_plan: Plan):
    response = await client.post(
        "/auth/register",
        json={
            "name": "User",
            "email": "user@example.com",
            "password": "short",
            "plan_id": str(test_plan.id),
        },
    )
    assert response.status_code == 422
