import uuid

import pytest
from httpx import AsyncClient

from app.models.plan import Plan
from app.models.user import User


@pytest.mark.asyncio
async def test_create_genre(admin_client: AsyncClient):
    response = await admin_client.post("/genres", json={"name": "Action"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Action"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_genre_duplicate(admin_client: AsyncClient):
    await admin_client.post("/genres", json={"name": "Drama"})
    response = await admin_client.post("/genres", json={"name": "Drama"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_genres(auth_client: AsyncClient, admin_client: AsyncClient):
    await admin_client.post("/genres", json={"name": "Comedy"})
    response = await auth_client.get("/genres")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_create_category(admin_client: AsyncClient):
    response = await admin_client.post("/categories", json={"name": "Documentary"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Documentary"


@pytest.mark.asyncio
async def test_create_plan(admin_client: AsyncClient):
    response = await admin_client.post("/plans", json={"name": "Gold"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Gold"


@pytest.mark.asyncio
async def test_user_cannot_create_genre(auth_client: AsyncClient):
    response = await auth_client.post("/genres", json={"name": "Horror"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_and_list_video(admin_client: AsyncClient):
    # Create genre and category first
    genre_resp = await admin_client.post("/genres", json={"name": "Sci-Fi"})
    genre_id = genre_resp.json()["id"]

    cat_resp = await admin_client.post("/categories", json={"name": "Film"})
    cat_id = cat_resp.json()["id"]

    # Create video
    video_resp = await admin_client.post(
        "/videos",
        json={
            "title": "Test Video",
            "description": "A test video",
            "url": "https://example.com/video.mp4",
            "duration_seconds": 3600,
            "genre_ids": [genre_id],
            "category_ids": [cat_id],
        },
    )
    assert video_resp.status_code == 201
    video_data = video_resp.json()
    assert video_data["title"] == "Test Video"
    assert len(video_data["genres"]) == 1
    assert len(video_data["categories"]) == 1

    # List videos
    list_resp = await admin_client.get("/videos")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_search_videos(admin_client: AsyncClient):
    # Create genre and category
    genre_resp = await admin_client.post("/genres", json={"name": "Thriller"})
    genre_id = genre_resp.json()["id"]
    cat_resp = await admin_client.post("/categories", json={"name": "Series"})
    cat_id = cat_resp.json()["id"]

    # Create video
    await admin_client.post(
        "/videos",
        json={
            "title": "Breaking Bad",
            "url": "https://example.com/bb.mp4",
            "duration_seconds": 2700,
            "genre_ids": [genre_id],
            "category_ids": [cat_id],
        },
    )

    # Search by title
    response = await admin_client.get("/videos/search", params={"q": "breaking"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert "breaking" in data["items"][0]["title"].lower()


@pytest.mark.asyncio
async def test_delete_genre_in_use(admin_client: AsyncClient):
    # Create genre and category
    genre_resp = await admin_client.post("/genres", json={"name": "Romance"})
    genre_id = genre_resp.json()["id"]
    cat_resp = await admin_client.post("/categories", json={"name": "Short"})
    cat_id = cat_resp.json()["id"]

    # Create video using genre
    await admin_client.post(
        "/videos",
        json={
            "title": "Love Story",
            "url": "https://example.com/love.mp4",
            "duration_seconds": 1800,
            "genre_ids": [genre_id],
            "category_ids": [cat_id],
        },
    )

    # Try to delete genre in use
    response = await admin_client.delete(f"/genres/{genre_id}")
    assert response.status_code == 409
