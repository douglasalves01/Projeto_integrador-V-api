"""
E2E tests backed by a real PostgreSQL container.

Flow:
1. Start PostgreSQL with Testcontainers once per pytest session.
2. Run Alembic migrations against that container.
3. For each test, truncate tables and seed known data.
4. Exercise the FastAPI app through HTTPX/ASGI.
5. Stop and remove the container when pytest finishes.
"""

import uuid
import os
import json
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from urllib.parse import urlparse


def _configure_docker_for_testcontainers() -> None:
    desktop_socket = Path.home() / ".docker" / "desktop" / "docker.sock"
    if "DOCKER_HOST" not in os.environ and desktop_socket.exists():
        os.environ["DOCKER_HOST"] = f"unix://{desktop_socket}"
        os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


_configure_docker_for_testcontainers()

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.auth.hashing import hash_password
from app.auth.jwt import create_access_token
from app.database.session import get_db
from app.main import create_app
from app.models.category import Category
from app.models.genre import Genre
from app.models.plan import Plan
from app.models.user import User, UserRole
from app.models.video import Video


ROOT_DIR = Path(__file__).resolve().parents[2]
E2E_PG_STATE_FILE = ROOT_DIR / ".pytest_cache" / "e2e-pg.json"

TRUNCATE_TABLES = (
    "refresh_tokens",
    "recommendations",
    "interaction_logs",
    "favorites",
    "watch_sessions",
    "video_categories",
    "video_genres",
    "videos",
    "users",
    "categories",
    "genres",
    "plans",
)


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    container_name = f"api-projeto-integrador-e2e-postgres-{uuid.uuid4().hex[:8]}"
    container = PostgresContainer(
        "postgres:16-alpine",
        username="e2e",
        password="e2e",
        dbname="e2e",
        driver="asyncpg",
    ).with_name(container_name)
    with container as postgres:
        E2E_PG_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        E2E_PG_STATE_FILE.write_text(
            json.dumps(
                {
                    "databaseUrl": postgres.get_connection_url(),
                    "containerName": container_name,
                }
            ),
            encoding="utf8",
        )
        try:
            yield postgres
        finally:
            E2E_PG_STATE_FILE.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    if not E2E_PG_STATE_FILE.exists():
        raise RuntimeError(
            f"E2E protection: Testcontainers state file missing ({E2E_PG_STATE_FILE})."
        )

    state = json.loads(E2E_PG_STATE_FILE.read_text(encoding="utf8"))
    database_url = state.get("databaseUrl")
    if not database_url:
        raise RuntimeError(f"Invalid e2e state file: {E2E_PG_STATE_FILE}")

    parsed = urlparse(database_url)
    db_name = parsed.path.removeprefix("/")
    if parsed.scheme != "postgresql+asyncpg" or parsed.hostname not in {"localhost", "127.0.0.1"} or db_name != "e2e":
        raise RuntimeError(
            f"E2E protection: database URL does not look like the ephemeral Testcontainers DB ({database_url})."
        )

    return database_url


@pytest.fixture(scope="session", autouse=True)
def migrated_database(database_url: str) -> None:
    alembic_cfg = Config(str(ROOT_DIR / "alembic.ini"))
    alembic_cfg.attributes["database_url"] = database_url
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture
async def engine(database_url: str, migrated_database):
    engine_ = create_async_engine(database_url, echo=False, future=True)
    try:
        yield engine_
    finally:
        await engine_.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    async with engine.begin() as conn:
        table_list = ", ".join(TRUNCATE_TABLES)
        await conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))

    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_data(session_factory):
    async with session_factory() as session:
        plans = [
            Plan(id=uuid.uuid4(), name="Basic"),
            Plan(id=uuid.uuid4(), name="Standard"),
            Plan(id=uuid.uuid4(), name="Premium"),
        ]
        session.add_all(plans)

        genres = [
            Genre(id=uuid.uuid4(), name="Science Fiction"),
            Genre(id=uuid.uuid4(), name="Drama"),
            Genre(id=uuid.uuid4(), name="Comedy"),
            Genre(id=uuid.uuid4(), name="Action"),
        ]
        session.add_all(genres)

        categories = [
            Category(id=uuid.uuid4(), name="Documentary"),
            Category(id=uuid.uuid4(), name="Short Film"),
            Category(id=uuid.uuid4(), name="Series"),
            Category(id=uuid.uuid4(), name="Feature Film"),
        ]
        session.add_all(categories)

        await session.flush()

        videos_data = [
            ("The Future of AI", 5400, [genres[0]], [categories[0]]),
            ("Lost in Time", 3600, [genres[0], genres[1]], [categories[2]]),
            ("Comedy Night Live", 7200, [genres[2]], [categories[3]]),
            ("Space Warriors", 6000, [genres[0], genres[3]], [categories[3]]),
            ("The Human Story", 1800, [genres[1]], [categories[1]]),
        ]
        videos = []
        for title, duration, video_genres, video_categories in videos_data:
            video = Video(
                id=uuid.uuid4(),
                title=title,
                description=f"Description for {title}",
                url=f"https://streaming.example.com/{title.lower().replace(' ', '-')}",
                duration_seconds=duration,
            )
            video.genres = video_genres
            video.categories = video_categories
            session.add(video)
            videos.append(video)

        user = User(
            id=uuid.uuid4(),
            name="Test User",
            email="testuser@e2e.com",
            password_hash=hash_password("userpass123"),
            role=UserRole.USER,
            plan_id=plans[0].id,
            is_active=True,
        )
        session.add(user)

        admin = User(
            id=uuid.uuid4(),
            name="Admin User",
            email="admin@e2e.com",
            password_hash=hash_password("adminpass123"),
            role=UserRole.ADMIN,
            plan_id=plans[2].id,
            is_active=True,
        )
        session.add(admin)

        await session.commit()

    return {
        "plans": [{"id": plan.id, "name": plan.name} for plan in plans],
        "genres": [{"id": genre.id, "name": genre.name} for genre in genres],
        "categories": [{"id": category.id, "name": category.name} for category in categories],
        "videos": [
            {"id": video.id, "title": video.title, "duration_seconds": video.duration_seconds}
            for video in videos
        ],
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": "USER",
            "password": "userpass123",
        },
        "admin": {
            "id": admin.id,
            "email": admin.email,
            "name": admin.name,
            "role": "ADMIN",
            "password": "adminpass123",
        },
    }


@pytest_asyncio.fixture
async def app(session_factory, seed_data):
    application = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def user_client(app, seed_data) -> AsyncGenerator[AsyncClient, None]:
    token = create_access_token(str(seed_data["user"]["id"]), "USER")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac


@pytest_asyncio.fixture
async def admin_client(app, seed_data) -> AsyncGenerator[AsyncClient, None]:
    token = create_access_token(str(seed_data["admin"]["id"]), "ADMIN")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac
