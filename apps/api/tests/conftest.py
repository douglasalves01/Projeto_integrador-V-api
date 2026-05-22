import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database.base import Base
from app.database.session import get_db
from app.main import create_app
from app.models.user import User, UserRole
from app.models.plan import Plan
from app.auth.hashing import hash_password
from app.auth.jwt import create_access_token

# Use SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database(request):
    if "tests/e2e" in str(request.node.path):
        yield
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_plan(db_session: AsyncSession) -> Plan:
    plan = Plan(id=uuid.uuid4(), name="Test Plan")
    db_session.add(plan)
    await db_session.flush()
    await db_session.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_plan: Plan) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email="testuser@example.com",
        password_hash=hash_password("testpassword123"),
        role=UserRole.USER,
        plan_id=test_plan.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession, test_plan: Plan) -> User:
    admin = User(
        id=uuid.uuid4(),
        name="Admin User",
        email="admin@example.com",
        password_hash=hash_password("adminpassword123"),
        role=UserRole.ADMIN,
        plan_id=test_plan.id,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def user_token(test_user: User) -> str:
    return create_access_token(str(test_user.id), test_user.role.value)


@pytest_asyncio.fixture
async def admin_token(test_admin: User) -> str:
    return create_access_token(str(test_admin.id), test_admin.role.value)


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, user_token: str) -> AsyncClient:
    client.headers["Authorization"] = f"Bearer {user_token}"
    return client


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, admin_token: str) -> AsyncClient:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    return client
