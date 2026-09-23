"""Shared fixtures for coordinator-api integration tests."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session, SQLModel

# Point the app at a throwaway DB and disable auth middleware before importing main.
os.environ.setdefault("URL", "sqlite:////tmp/aitbc-coordinator-test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-for-coordinator-tests" * 2)
os.environ.setdefault("TEST_MODE", "true")

os.environ.setdefault("EXPLORER_API_URL", "http://127.0.0.1:8100/health")
os.environ.setdefault("MARKET_STATS_URL", "http://127.0.0.1:8102/health")
os.environ.setdefault("ECON_STATS_URL", "http://127.0.0.1:8104/health")
os.environ.setdefault("MARKET_HEALTH_URL", "http://127.0.0.1:8102/health")
os.environ.setdefault("MARKET_HEALTH_URL_ALT", "http://127.0.0.1:8104/health")
os.environ.setdefault("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
os.environ.setdefault("COORDINATOR_HEALTH_URL", "http://127.0.0.1:8203/health")

from coordinator_api.main import app  # noqa: E402
from coordinator_api.storage import get_session  # noqa: E402


@pytest.fixture
def db_engine():
    """Create a fresh in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine) -> Generator[Session]:
    """Yield a database session bound to the in-memory engine."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _seed_client_refs(db_session):
    """Seed the bare-name client refs the job/payment tests use.

    resolve_client no longer provisions placeholder users for arbitrary
    strings (GAP-59) -- only wallet addresses auto-create. Tests that call
    create_job(client_id="client1") need the ref to name a real user; seeding
    by id makes resolution return the ref unchanged, so stored client_id and
    client_ref match what the tests were written against.
    """
    from coordinator_api.contexts.infrastructure.domain.user import User

    for ref in ("client1", "client-1"):
        db_session.add(User(id=ref, email=f"{ref}@example.com", username=ref))
    db_session.commit()


@pytest.fixture
def client(db_session):
    """Yield a TestClient that uses the in-memory DB session."""
    from fastapi.testclient import TestClient

    def override_get_session() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
