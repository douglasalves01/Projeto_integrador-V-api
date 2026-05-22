"""E2E environment checks."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_e2e_database_uses_testcontainers_postgres(database_url, engine):
    assert database_url.startswith("postgresql+asyncpg://")
    assert "sqlite" not in database_url
    assert "test.db" not in database_url
    assert engine.dialect.name == "postgresql"

    async with engine.connect() as conn:
        result = await conn.execute(text("select current_database(), version()"))
        database_name, database_version = result.one()

    assert database_name == "e2e"
    assert "PostgreSQL" in database_version
