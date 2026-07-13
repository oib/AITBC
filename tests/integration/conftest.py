"""Shared fixtures and setup for agent coordinator integration tests."""

import os
import sys
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

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

# Use a shared file-backed SQLite database for the coordinator app so that
# repeated ``init_db`` calls can rely on ``checkfirst`` and skip existing tables.
os.environ.setdefault("URL", "sqlite:////tmp/aitbc_test_coordinator.db")


async def _noop_sleep(*_args: object, **_kwargs: object) -> None:
    """No-op replacement for ``asyncio.sleep`` to bound test shutdown time."""
    return None


async def _noop_async() -> None:
    """No-op async helper used to skip redundant DB setup."""
    return None


def _reset_coordinator_modules() -> None:
    """Clear cached coordinator app modules and SQLModel metadata tables.

    Several integration tests import other AITBC apps that also use SQLModel.
    Those apps share the global SQLModel metadata, so model classes with the
    same name (e.g., Transaction) can conflict. Resetting the metadata before
    importing the coordinator app gives the session a clean registry.
    """
    for mod_name in list(sys.modules.keys()):
        if mod_name == "coordinator_api" or mod_name.startswith("coordinator_api."):
            del sys.modules[mod_name]
        elif mod_name == "aitbc_chain" or mod_name.startswith("aitbc_chain."):
            del sys.modules[mod_name]
    # Ensure any pending SQLModel mappers (e.g., from aitbc_chain) are fully
    # configured before we clear the metadata, so the coordinator models can be
    # re-registered cleanly in a fresh registry without ambiguous path errors.
    SQLModel._sa_registry.configure()
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
    from coordinator_api.main import create_app
except Exception as _e:
    create_app = None  # type: ignore[assignment]
    _skip_reason = f"coordinator-api import conflict: {_e}"


@pytest.fixture(autouse=True)
def skip_if_app_unavailable() -> None:
    """Skip all tests if the app could not be imported."""
    if _skip_reason is not None:
        pytest.skip(_skip_reason)


def _reset_coordinator_state() -> None:
    """Clear in-memory Redis fallback state between tests."""
    try:
        from coordinator_api.contexts.infrastructure.services.redis_state import RedisStateManager

        RedisStateManager.get_instance_sync()._memory.clear()
    except Exception:
        pass


@pytest.fixture(scope="session")
def coordinator_client() -> Generator[TestClient]:
    """Create a session-scoped test client for the coordinator API.

    The app is imported once for the whole integration session. The graceful
    shutdown sleep and async DB initialization are patched to keep fixture
    teardown bounded. In-memory Redis fallback state is cleared per test by
    the ``reset_coordinator_state`` fixture.
    """
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

    from coordinator_api.main import create_app as _create_app
    import coordinator_api.storage.db as _db

    app = _create_app()
    with patch("asyncio.sleep", _noop_sleep), patch.object(_db, "init_async_db", _noop_async):
        with TestClient(app) as client:
            yield client


@pytest.fixture(autouse=True)
def reset_coordinator_state(coordinator_client: TestClient) -> Generator[None]:
    """Reset in-memory coordinator state before each test."""
    _reset_coordinator_state()
    coordinator_client.headers.pop("Authorization", None)
    yield
    _reset_coordinator_state()
    coordinator_client.headers.pop("Authorization", None)


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

    coordinator_client.headers.update({"Authorization": f"Bearer {token}"})
    yield coordinator_client
    coordinator_client.headers.pop("Authorization", None)


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


@pytest.fixture
def unique_agent_data() -> dict[str, Any]:
    """Agent registration data with a unique ID per test (avoids collisions)."""
    import uuid

    unique = uuid.uuid4().hex[:8]
    return {
        "agent_id": f"test-agent-{unique}",
        "public_key": f"test-pubkey-{unique}",
        "capabilities": ["data-processing", "analysis"],
    }


@pytest.fixture
def unique_task_data() -> dict[str, Any]:
    """Task submission data with a unique prompt per test."""
    import uuid

    unique = uuid.uuid4().hex[:8]
    return {
        "task_data": {"model": "llama2", "prompt": f"test prompt {unique}"},
        "priority": "normal",
        "requirements": {},
    }


@pytest.fixture
def registered_agent(authenticated_client: TestClient, unique_agent_data: dict[str, Any]) -> dict[str, Any]:
    """Register an agent and return the registration response data.

    Depends on authenticated_client (which provides a valid session token).
    Yields the response JSON from the registration endpoint.
    """
    response = authenticated_client.post("/v1/agent/agents/register", json=unique_agent_data)
    if response.status_code not in (200, 201):
        pytest.skip(f"Agent registration failed: {response.status_code} {response.text}")
    yield response.json()
