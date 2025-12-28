"""Database configuration for the coordinator API."""

from sqlmodel import create_engine, SQLModel
from sqlalchemy import StaticPool

# Create in-memory SQLite database for now
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)


def create_db_and_tables():
    """Create database and tables"""
    SQLModel.metadata.create_all(engine)
