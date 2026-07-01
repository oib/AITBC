"""Shared database utilities for AITBC services."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlmodel import Session as SQLModelSession

from .config import ServiceSettings

Base = declarative_base()


def get_engine(settings: ServiceSettings) -> Engine:
    """Create SQLAlchemy engine based on configuration."""
    db_config = settings.database
    return create_engine(
        db_config.effective_url,
        pool_size=db_config.pool_size,
        max_overflow=db_config.max_overflow,
        pool_pre_ping=db_config.pool_pre_ping,
        echo=settings.debug,
    )


def get_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    """Create session factory. Uses SQLModel Session class so .exec() is available."""
    return sessionmaker[Session](bind=engine, autoflush=False, autocommit=False, class_=SQLModelSession)


def get_db(engine: Engine) -> Generator[Session]:
    """Dependency for FastAPI endpoints."""
    Session = get_sessionmaker(engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
