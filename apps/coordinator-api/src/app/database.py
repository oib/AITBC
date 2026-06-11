"""Database configuration for the coordinator API."""

from sqlalchemy import StaticPool
from sqlmodel import SQLModel, create_engine

from .config import settings

# Create database engine using URL from config with performance optimizations
if settings.get_effective_database_url().startswith("sqlite"):
    engine = create_engine(
        settings.get_effective_database_url(),
        connect_args={
            "check_same_thread": False,
            "timeout": 30
        },
        poolclass=StaticPool,
        echo=settings.database_echo,
        pool_pre_ping=settings.database_pool_pre_ping,
    )
else:
    # PostgreSQL/MySQL with connection pooling using config values
    engine = create_engine(
        settings.get_effective_database_url(),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=settings.database_pool_pre_ping,
        pool_recycle=settings.database_pool_recycle,
        echo=settings.database_echo,
    )


def create_db_and_tables() -> None:
    """Create database and tables"""
    SQLModel.metadata.create_all(engine)


async def init_db() -> None:
    """Initialize database by creating tables"""
    create_db_and_tables()
