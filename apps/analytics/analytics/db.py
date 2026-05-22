"""Sessao Postgres sincrona — analytics nao precisa de async."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from analytics.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
