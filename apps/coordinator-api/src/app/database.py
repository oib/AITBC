"""Database configuration for the coordinator API."""

from sqlalchemy import StaticPool
from sqlmodel import SQLModel, create_engine

from .config import settings

# Create database engine using URL from config with performance optimizations
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={
            "check_same_thread": False,
            "timeout": 30
        },
        poolclass=StaticPool,
        echo=settings.test_mode,  # Enable SQL logging for debugging in test mode
        pool_pre_ping=True,  # Verify connections before using
    )
else:
    # PostgreSQL/MySQL with connection pooling
    engine = create_engine(
        settings.database_url,
        pool_size=10,  # Number of connections to maintain
        max_overflow=20,  # Additional connections when pool is exhausted
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
        echo=settings.test_mode,  # Enable SQL logging for debugging in test mode
    )


def create_db_and_tables():
    """Create database and tables"""
    SQLModel.metadata.create_all(engine)


async def init_db():
    """Initialize database by creating tables"""
    create_db_and_tables()
