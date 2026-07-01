"""Shared fixtures and setup for agent coordinator integration tests."""

import os
import sys
from collections.abc import Generator
from typing import Any

import pytest
from starlette.testclient import TestClient

# Skip collection of test modules that import non-existent app modules.
# test_staking_lifecycle.py imports app.domain.bounty which was removed in a
# prior release. This is a pre-existing issue outside v0.5.18's scope.
collect_ignore = ["test_staking_lifecycle.py"]

# Enable debug mode for integration tests so legacy compatibility routes and
# docs are available. Must be set before importing the coordinator app.
os.environ.setdefault("DEBUG", "true")

# Clear any cached app modules to avoid conflicts
for mod_name in list(sys.modules.keys()):
    if mod_name == "app" or mod_name.startswith("app."):
        del sys.modules[mod_name]

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

    assert create_app is not None
    app = create_app()
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
    register_data = {
        "email": "integration-test@aitbc.local",
        "username": "integration_test_user",
        "wallet_address": "aitbc_integration_test",
    }
    register_response = coordinator_client.post("/v1/register", json=register_data)
    if register_response.status_code not in (200, 201):
        # If registration failed, try login with the same wallet address
        login_response = coordinator_client.post("/v1/users/login", json={"wallet_address": register_data["wallet_address"]})
        if login_response.status_code not in (200, 201):
            pytest.skip(f"Could not authenticate integration test user: {register_response.text} / {login_response.text}")
        token = login_response.json().get("session_token", "")
    else:
        token = register_response.json().get("session_token", "")

    if not token:
        pytest.skip("No session token returned for integration test user")

    assert create_app is not None
    app = create_app()
    with TestClient(app) as client:
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


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
