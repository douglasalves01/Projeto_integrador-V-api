"""Shared pytest fixtures: SQLite in-memory DB, JWT, models, Redis cache."""

from __future__ import annotations

import os

os.environ.setdefault("LLM_ENABLED", "false")
os.environ.setdefault("VODCHAT_ENABLED", "false")

from collections.abc import Generator
from datetime import datetime, timezone
from uuid import UUID

import pandas as pd
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from jose import jwt
from scipy.sparse import csr_matrix
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

get_settings.cache_clear()
from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.collaborative import CollaborativeRecommender
from app.models.content_based import ContentBasedRecommender
from app.models.hybrid import HybridRecommender
from app.models.schemas_db import (
    Base,
    Category,
    Content,
    ContentCategory,
    ContentGenre,
    Genre,
    User,
    UserProfileAI,
    ViewHistory,
)
from app.schemas.health import DependencyStatus
from app.services import model_loader as model_loader_module

settings = get_settings()

TEST_USER_UUID = UUID(int=1)
OTHER_USER_UUID = UUID(int=999)

# In-memory Redis substitute for API cache tests
_recs_cache: dict[str, dict] = {}


@pytest.fixture(scope="session")
def jwt_secret() -> str:
    return settings.JWT_SECRET


@pytest.fixture
def auth_token(jwt_secret: str, test_user_id: int = 1) -> str:
    return jwt.encode(
        {"sub": str(test_user_id), "user_id": test_user_id},
        jwt_secret,
        algorithm=settings.JWT_ALGORITHM,
    )


@pytest.fixture
def llm_auth_token(jwt_secret: str) -> str:
    return jwt.encode(
        {"sub": str(TEST_USER_UUID), "user_id": str(TEST_USER_UUID)},
        jwt_secret,
        algorithm=settings.JWT_ALGORITHM,
    )


@pytest.fixture
def llm_auth_headers(llm_auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {llm_auth_token}"}


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    """Seed minimal catalog and viewing data for API tests."""
    action = Genre(name="Ação")
    comedy = Genre(name="Comédia")
    movies = Category(name="Filmes")
    db_session.add_all([action, comedy, movies])
    db_session.flush()

    contents = [
        Content(
            title=f"Title {i}",
            description=f"Description {i} ação comédia",
            duration_sec=3600,
            release_year=2020 + i,
            created_at=datetime.now(timezone.utc),
        )
        for i in range(1, 6)
    ]
    db_session.add_all(contents)
    db_session.flush()

    for idx, content in enumerate(contents):
        db_session.add(ContentGenre(content_id=content.id, genre_id=action.id if idx % 2 else comedy.id))
        db_session.add(ContentCategory(content_id=content.id, category_id=movies.id))

    user = User(email="user@test.com", name="Test User", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    db_session.flush()

    profile = UserProfileAI(
        user_id=user.id,
        genre_weights={"Ação": 0.5},
        category_weights={"Filmes": 0.3},
        total_views=3,
        last_updated=datetime.now(timezone.utc),
    )
    db_session.add(profile)

    for content in contents[:3]:
        db_session.add(
            ViewHistory(
                user_id=user.id,
                content_id=content.id,
                watched_sec=1800,
                total_sec=3600,
                completion=0.5,
                started_at=datetime.now(timezone.utc),
                ended_at=datetime.now(timezone.utc),
            )
        )

    db_session.commit()

    from app.services import catalog_loader

    catalog_loader.load_catalog_from_db(db_session)
    return db_session


@pytest.fixture
def catalog_df_5() -> pd.DataFrame:
    """Five contents for content-based tests (min_df=2 compatible)."""
    return pd.DataFrame(
        {
            "content_id": [1, 2, 3, 4, 5],
            "text_doc": [
                "ação aventura herói",
                "ação explosão perseguição",
                "comédia romance leve",
                "ação aventura espaço",
                "documentário natureza",
            ],
            "genres": [
                "Ação,Aventura",
                "Ação",
                "Comédia,Romance",
                "Ação,Aventura",
                "Documentário",
            ],
            "popularity": [10.0, 8.0, 5.0, 12.0, 3.0],
        }
    )


@pytest.fixture
def fitted_models(catalog_df_5: pd.DataFrame, tmp_path):
    """Train small CB/CF models for integration-style API tests."""
    cb = ContentBasedRecommender()
    cb.fit(catalog_df_5)

    rows, cols, data = [], [], []
    for user_idx in range(10):
        for item_idx in range(min(5, 20)):
            if (user_idx + item_idx) % 3 == 0:
                rows.append(user_idx)
                cols.append(item_idx % 5)
                data.append(1.0)
    matrix = csr_matrix((data, (rows, cols)), shape=(10, 5))
    user_mapping = {100 + i: i for i in range(10)}
    content_mapping = {cid: i for i, cid in enumerate(catalog_df_5["content_id"])}

    cf = CollaborativeRecommender(factors=8, regularization=0.05, iterations=5)
    cf.fit(matrix, user_mapping, content_mapping)

    hybrid = HybridRecommender(cb, cf)
    loader = model_loader_module.model_loader
    loader.content_based = cb
    loader.collaborative = cf
    loader.hybrid = hybrid
    loader.current_model_version = "hybrid-v1.0.0-test"

    yield {"cb": cb, "cf": cf, "hybrid": hybrid}

    loader.content_based = None
    loader.collaborative = None
    loader.hybrid = None


@pytest.fixture
def mock_redis_cache(monkeypatch):
    """Replace Redis cache with in-memory dict."""

    async def _get(user_id, k):
        return _recs_cache.get(f"recs:{user_id}:k{k}")

    async def _set(user_id, k, data, ttl=None):
        _recs_cache[f"recs:{user_id}:k{k}"] = data

    async def _invalidate(user_id):
        keys = [key for key in _recs_cache if key.startswith(f"recs:{user_id}:")]
        for key in keys:
            del _recs_cache[key]
        return len(keys)

    async def _ping():
        return True

    _recs_cache.clear()
    targets = [
        "app.core.cache.get_cached_recs",
        "app.core.cache.set_cached_recs",
        "app.core.cache.invalidate_user_recs_cache",
        "app.services.recommendation_service.get_cached_recs",
        "app.services.recommendation_service.set_cached_recs",
        "app.api.routes.profile.invalidate_user_recs_cache",
    ]
    for target in targets:
        if "get_cached" in target:
            monkeypatch.setattr(target, _get)
        elif "set_cached" in target:
            monkeypatch.setattr(target, _set)
        elif "invalidate" in target:
            monkeypatch.setattr(target, _invalidate)
    monkeypatch.setattr("app.core.cache.ping_redis", _ping)
    yield _recs_cache
    _recs_cache.clear()


@pytest.fixture
def test_client(
    seeded_db: Session,
    fitted_models,
    mock_redis_cache,
    monkeypatch,
) -> Generator[TestClient, None, None]:
    def _override_db() -> Generator[Session, None, None]:
        yield seeded_db

    async def _override_user(request: Request) -> dict:
        request.state.user_id = 1
        if isinstance(request.scope.get("state"), dict):
            request.scope["state"]["user_id"] = 1
        return {"sub": "1", "_user_id": 1, "user_id": 1}

    monkeypatch.setattr(
        "app.api.routes.health._check_mysql",
        lambda: DependencyStatus(status="up"),
    )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    def _load_preserving_fitted_models() -> bool:
        loader = model_loader_module.model_loader
        if loader.hybrid is not None:
            return True
        return model_loader_module.ModelLoader.load(loader)

    monkeypatch.setattr(model_loader_module.model_loader, "load", _load_preserving_fitted_models)

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def llm_test_client(
    seeded_db: Session,
    fitted_models,
    mock_redis_cache,
    monkeypatch,
) -> Generator[TestClient, None, None]:
    def _override_db() -> Generator[Session, None, None]:
        yield seeded_db

    async def _override_user(request: Request) -> dict:
        request.state.user_id = str(TEST_USER_UUID)
        if isinstance(request.scope.get("state"), dict):
            request.scope["state"]["user_id"] = str(TEST_USER_UUID)
        return {
            "sub": str(TEST_USER_UUID),
            "_user_id": str(TEST_USER_UUID),
            "user_id": str(TEST_USER_UUID),
        }

    monkeypatch.setattr(
        "app.api.routes.health._check_mysql",
        lambda: DependencyStatus(status="up"),
    )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    def _load_preserving_fitted_models() -> bool:
        loader = model_loader_module.model_loader
        if loader.hybrid is not None:
            return True
        return model_loader_module.ModelLoader.load(loader)

    monkeypatch.setattr(model_loader_module.model_loader, "load", _load_preserving_fitted_models)

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
