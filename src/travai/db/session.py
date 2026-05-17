"""Databas-engine och session-hantering."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from travai.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Kontexthanterad session som auto-committar eller rollbackar."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
