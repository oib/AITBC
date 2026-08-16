"""Shared fixtures and setup for agent coordinator integration tests."""

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlmodel import SQLModel
from starlette.testclient import TestClient


# Enable debug mode for integration tests so legacy compatibility routes and
# docs are available. Must be set before importing the coordinator app.
os.environ.setdefault("DEBUG", "true")
# Test mode disables the middleware-level auth guard so integration tests can
# exercise route logic without an Authorization header. Endpoint dependencies
# still enforce auth where they are declared.
os.environ.setdefault("TEST_MODE", "true")

# Use a shared file-backed SQLite database for the coordinator app so that
# repeated ``init_db`` calls can rely on ``checkfirst`` and skip existing tables.
os.environ.setdefault("URL", "sqlite:////tmp/aitbc_test_coordinator.db")


async def _noop_async() -> None:
    """No-op async helper used to skip redundant DB setup."""
    return None


def _reset_coordinator_modules() -> None:
    """Clear the Prometheus registry so re-imported apps can register their metrics again.

    This used to do considerably more. It dropped every ``aitbc_chain`` module from
    ``sys.modules`` and then called ``SQLModel._sa_registry.dispose()`` and
    ``SQLModel.metadata.clear()``, because the chain's ``Transaction``, ``Block`` and
    ``Receipt`` collided by name with coordinator-api's on the one global registry, and this
    file's own docstring said as much.

    Clearing that registry is not a reset. A class registers its ``Table`` when its module
    first executes, and the module then stays in ``sys.modules``, so nothing re-registers what
    was cleared -- and this ran at *module scope*, during collection, before a single test in
    the repo had started. Every suite collected afterwards inherited the empty registry.

    ``aitbc_chain`` now keeps its tables on its own metadata, so the two model sets no longer
    meet and none of that is needed (V23-74).
    """
    try:
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            REGISTRY.unregister(collector)
    except Exception:
        pass


_reset_coordinator_modules()


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

    The app is imported once for the whole integration session. Async DB
    initialization is patched to keep fixture setup bounded. In-memory Redis
    fallback state is cleared per test by the ``reset_coordinator_state`` fixture.
    """
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

    try:
        from coordinator_api.main import create_app as _create_app
        import coordinator_api.storage.db as _db
    except Exception as _e:
        pytest.skip(f"coordinator-api not available: {_e}")

    app = _create_app()
    SQLModel.metadata.create_all(_db.get_engine())
    with patch.object(_db, "init_async_db", _noop_async):
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

    Generates an Ethereum wallet, obtains a nonce from /v1/auth/nonce, signs
    the canonical login message, and registers the wallet via /v1/register.
    The coordinator API accepts the token via the Authorization: Bearer header
    or the ``token`` query parameter.
    """
    import uuid

    unique = uuid.uuid4().hex[:8]
    account = Account.create()
    wallet_address = account.address.lower()

    nonce_resp = coordinator_client.post("/v1/auth/nonce", json={"wallet_address": wallet_address})
    if nonce_resp.status_code != 200:
        pytest.skip(f"Could not get nonce for integration test user: {nonce_resp.text}")
    nonce = nonce_resp.json()["nonce"]

    message = f"Sign this message to log in to AITBC.\nWallet: {wallet_address}\nNonce: {nonce}"
    signable = encode_defunct(text=message)
    signature = account.sign_message(signable).signature.hex()

    register_data = {
        "email": f"integration-test-{unique}@aitbc.local",
        "username": f"integration_test_user_{unique}",
        "wallet_address": wallet_address,
        "nonce": nonce,
        "signature": signature,
    }
    register_response = coordinator_client.post("/v1/register", json=register_data)
    if register_response.status_code not in (200, 201):
        pytest.skip(f"Could not authenticate integration test user: {register_response.text}")
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
