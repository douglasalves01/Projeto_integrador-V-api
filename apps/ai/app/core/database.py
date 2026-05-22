from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, TimeoutError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import DatabaseTimeoutError
from app.models.schemas_db import Base  # noqa: F401 — registers ORM models

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    connect_args={
        "connect_timeout": settings.DB_CONNECT_TIMEOUT,
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except (TimeoutError, OperationalError) as exc:
        db.rollback()
        if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
            raise DatabaseTimeoutError() from exc
        raise
    finally:
        db.close()
