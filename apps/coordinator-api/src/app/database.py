"""Database configuration for the coordinator API."""

from sqlmodel import create_engine, SQLModel
from sqlalchemy import StaticPool
from .config import settings

# Create database engine using URL from config
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    poolclass=StaticPool if settings.database_url.startswith("sqlite") else None,
    echo=settings.test_mode  # Enable SQL logging for debugging in test mode
)


def create_db_and_tables():
    """Create database and tables"""
    SQLModel.metadata.create_all(engine)

async def init_db():
    """Initialize database by creating tables"""
    create_db_and_tables()
