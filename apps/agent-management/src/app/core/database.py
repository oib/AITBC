"""Shared database utilities for AITBC services."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator

from .config import ServiceSettings

Base = declarative_base()


def get_engine(settings: ServiceSettings):
    """Create SQLAlchemy engine based on configuration."""
    db_config = settings.database
    return create_engine(
        db_config.effective_url,
        pool_size=db_config.pool_size,
        max_overflow=db_config.max_overflow,
        pool_pre_ping=db_config.pool_pre_ping,
        echo=settings.debug
    )


def get_sessionmaker(engine):
    """Create session factory."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db(engine) -> Generator:
    """Dependency for FastAPI endpoints."""
    Session = get_sessionmaker(engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
