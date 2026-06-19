"""Ensure coordinator-api src is on sys.path for all tests in this directory."""

import os
from pathlib import Path

import pytest

# Set up test environment
os.environ["TEST_MODE"] = "true"
os.environ["DEBUG"] = "true"  # Enable debug mode for mock endpoints
os.environ["ENABLE_MOCK_TRAINING"] = "true"  # Enable mock training endpoints
project_root = Path(__file__).resolve().parent.parent.parent
os.environ["AUDIT_LOG_DIR"] = str(project_root / "logs" / "audit")
os.environ["TEST_DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="function")
def client():
    """Create a TestClient for API testing."""
    from app.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)
