"""Reusable builder fixtures for integration tests (v0.16.1 §B4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _coordinator_app():
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    src = str(repo_root / "apps" / "coordinator-api" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from coordinator_api.main import app

    return app


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient for the coordinator API."""
    return TestClient(_coordinator_app())


@pytest.fixture
def developer_payload() -> dict[str, str]:
    """Return a valid developer registration payload."""
    return {
        "wallet_address": "0x1234567890abcdef",
        "name": "Builder One",
        "email": "builder@example.com",
        "github_handle": "builder1",
    }


@pytest.fixture
def grant_payload(developer_payload: dict[str, str]) -> dict[str, str]:
    """Return a valid grant proposal payload."""
    return {
        "title": "Example Grant",
        "description": "A test grant proposal",
        "requested_amount": "1000.00",
        "voting_days": "7",
        "developer_id": developer_payload["wallet_address"],
    }
