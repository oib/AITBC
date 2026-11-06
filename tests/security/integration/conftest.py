"""Shared fixtures for the security integration-pin tier.

FastAPI ``TestClient`` runs against the real coordinator-api and api-gateway
apps with throwaway in-memory SQLite — same pattern as the apps' own suites,
kept minimal: only what the security pins need.

Env vars are set before the app modules are imported (they are read into
module constants at import time). ``API_GATEWAY_KEY`` is pinned so the
gateway auth gate is exercisable; ``API_GATEWAY_REQUIRE_AUTH`` stays at its
secure default (``true``).
"""

from __future__ import annotations

import os
from collections.abc import Generator

os.environ.setdefault("URL", "sqlite:////tmp/aitbc-security-int-test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-for-coordinator-tests" * 2)
os.environ.setdefault("TEST_MODE", "true")
os.environ.setdefault("EXPLORER_API_URL", "http://127.0.0.1:8100/health")
os.environ.setdefault("MARKET_STATS_URL", "http://127.0.0.1:8102/health")
os.environ.setdefault("ECON_STATS_URL", "http://127.0.0.1:8104/health")
os.environ.setdefault("MARKET_HEALTH_URL", "http://127.0.0.1:8102/health")
os.environ.setdefault("MARKET_HEALTH_URL_ALT", "http://127.0.0.1:8104/health")
os.environ.setdefault("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
os.environ.setdefault("COORDINATOR_HEALTH_URL", "http://127.0.0.1:8203/health")
os.environ.setdefault("CHAIN_ID", "ait-testchain")
os.environ.setdefault("API_GATEWAY_KEY", "test-gateway-key-not-a-secret")
os.environ.setdefault("API_GATEWAY_RATE_LIMIT", "10000/minute")

import pytest  # noqa: E402
from sqlalchemy import StaticPool, create_engine  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from coordinator_api.main import app  # noqa: E402
from coordinator_api.storage import get_session  # noqa: E402


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine) -> Generator[Session]:
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def client(db_session):
    """TestClient bound to the in-memory DB session."""
    from fastapi.testclient import TestClient

    def override_get_session() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
