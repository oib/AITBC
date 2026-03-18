"""Database configuration for the coordinator API."""

from sqlmodel import create_engine, SQLModel
from sqlalchemy import StaticPool

# Create in-memory SQLite database for now
engine = create_engine(
    "sqlite:///./data/coordinator.db",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=True  # Enable SQL logging for debugging
)


def create_db_and_tables():
    """Create database and tables"""
    SQLModel.metadata.create_all(engine)

async def init_db():
    """Initialize database by creating tables"""
    create_db_and_tables()
