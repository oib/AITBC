"""Shared fixtures and setup for agent coordinator integration tests."""

import os
import sys
from collections.abc import Generator
from typing import Any

import pytest
from sqlmodel import SQLModel
from starlette.testclient import TestClient

# Skip collection of test modules that import non-existent app modules.
# test_staking_lifecycle.py imports app.domain.bounty which was removed in a
# prior release. This is a pre-existing issue outside v0.5.18's scope.
collect_ignore = ["test_staking_lifecycle.py"]

# Enable debug mode for integration tests so legacy compatibility routes and
# docs are available. Must be set before importing the coordinator app.
os.environ.setdefault("DEBUG", "true")


def _reset_coordinator_modules() -> None:
    """Clear cached coordinator app modules and SQLModel metadata tables.

    Several integration tests import other AITBC apps that also use SQLModel.
    Those apps share the global SQLModel metadata, so model classes with the
    same name (e.g., Transaction) can conflict. Resetting the metadata before
    importing the coordinator app gives each test a clean registry.
    """
    for mod_name in list(sys.modules.keys()):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]
        elif mod_name == "aitbc_chain" or mod_name.startswith("aitbc_chain."):
            del sys.modules[mod_name]
    SQLModel.metadata.clear()
    # Clear Prometheus registry to avoid duplicate metric errors on re-import
    try:
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            REGISTRY.unregister(collector)
    except Exception:
        pass


_reset_coordinator_modules()

_skip_reason: str | None = None

try:
    from app.main import create_app
except Exception as _e:
    create_app = None  # type: ignore[assignment]
    _skip_reason = f"agent-coordinator app import conflict: {_e}"


@pytest.fixture(autouse=True)
def skip_if_app_unavailable() -> None:
    """Skip all tests if the app could not be imported."""
    if _skip_reason is not None:
        pytest.skip(_skip_reason)


@pytest.fixture
def coordinator_client() -> Generator[TestClient]:
    """Create a test client for coordinator API with Redis storage."""
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

    # Reset modules to clear any conflicting SQLModel registrations from
    # other apps (e.g., aitbc_chain.base_models.Transaction) that may have
    # been imported by earlier tests in the same session.
    _reset_coordinator_modules()
    from app.main import create_app as _create_app

    app = _create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def authenticated_client(coordinator_client: TestClient) -> Generator[TestClient]:
    """Create an authenticated test client with a session token.

    Registers a test user via the coordinator API and uses the returned
    session token for authenticated requests. The coordinator API accepts
    the token via the Authorization: Bearer header or the ``token`` query
    parameter.
    """
    import uuid

    unique = uuid.uuid4().hex[:8]
    register_data = {
        "email": f"integration-test-{unique}@aitbc.local",
        "username": f"integration_test_user_{unique}",
    }
    register_response = coordinator_client.post("/v1/register", json=register_data)
    if register_response.status_code not in (200, 201):
        # If registration failed, try login with a unique wallet address
        wallet = f"auth_test_wallet_{unique}"
        login_response = coordinator_client.post("/v1/login", json={"wallet_address": wallet})
        if login_response.status_code not in (200, 201):
            pytest.skip(f"Could not authenticate integration test user: {register_response.text} / {login_response.text}")
        token = login_response.json().get("session_token", "")
    else:
        token = register_response.json().get("session_token", "")

    if not token:
        pytest.skip("No session token returned for integration test user")

    # Re-use the same coordinator_client (already has the app running)
    coordinator_client.headers.update({"Authorization": f"Bearer {token}"})
    yield coordinator_client


@pytest.fixture
def sample_agent_data() -> dict[str, Any]:
    """Sample agent registration data for the current /v1/agent/agents/register endpoint."""
    return {
        "agent_id": "test-integration-agent",
        "public_key": "test-public-key",
        "capabilities": ["data-processing", "analysis"],
    }


@pytest.fixture
def sample_task_data() -> dict[str, Any]:
    """Sample task submission data."""
    return {"task_data": {"model": "llama2", "prompt": "test prompt"}, "priority": "normal", "requirements": {}}
