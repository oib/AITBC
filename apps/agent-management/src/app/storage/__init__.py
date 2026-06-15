"""Storage module for AITBC Agent Management Service.

Provides database session management using SQLModel.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from aitbc import get_logger

from ..core.config import settings

logger = get_logger(__name__)
_engine: Engine | None = None


def get_engine() -> Engine:
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        database_url = settings.database.effective_url
        _engine = create_engine(database_url, echo=settings.debug)
        logger.info("Database engine created: %s", database_url)
    return _engine


def get_session() -> Generator[Session]:
    """Get a database session for dependency injection."""
    engine = get_engine()
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.close()
