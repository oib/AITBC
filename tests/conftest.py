"""
Minimal conftest for pytest discovery
Imports fixtures from dedicated fixture files for better organization
"""

import sys
from pathlib import Path

# Add coordinator-api src to path for tests that import app.main
_COORD_SRC = str(Path(__file__).resolve().parent.parent / "apps" / "coordinator-api" / "src")
if _COORD_SRC not in sys.path:
    sys.path.insert(0, _COORD_SRC)

# Add blockchain-node src to path for tests that import aitbc_chain
_BLOCKCHAIN_SRC = str(Path(__file__).resolve().parent.parent / "apps" / "blockchain-node" / "src")
if _BLOCKCHAIN_SRC not in sys.path:
    sys.path.insert(0, _BLOCKCHAIN_SRC)

# Add tests dir to path so fixture modules are importable
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import pytest  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from aitbc.training_setup import TrainingEnvironment, TrainingSetupError  # noqa: E402

# Register multi-chain and multi-node fixtures so they're available to all tests
from tests.fixtures.multi_chain import (  # noqa: E402,F401
    island_registry,
    mock_settings,
    multi_chain_mempool,
    multi_chain_setup,
    sync_source_map,
    three_chain_setup,
)
from tests.harness.multi_node import (  # noqa: E402,F401
    multi_node_harness,
    three_node_network,
)


@pytest.fixture(autouse=True)
def mock_ctx_obj(monkeypatch):
    """Auto-use fixture that patches CliRunner.invoke to set ctx.obj"""
    original_invoke = CliRunner.invoke

    def patched_invoke(self, cli, args, **kwargs):
        # Ensure obj is set with default context values
        if "obj" not in kwargs or kwargs["obj"] is None:
            kwargs["obj"] = {"output": "table", "url": None, "api_key": None, "verbose": 0, "debug": False}
        return original_invoke(self, cli, args, **kwargs)

    monkeypatch.setattr(CliRunner, "invoke", patched_invoke)


@pytest.fixture(scope="session")
def training_env():
    """
    Session-scoped fixture for training environment setup.
    Sets up the training environment once per test session.
    """
    env = TrainingEnvironment()
    try:
        # Temporarily skip prerequisites check to avoid hanging
        # env.check_prerequisites()
        yield env
    except TrainingSetupError as e:
        pytest.skip(f"Training prerequisites not met: {e}")


@pytest.fixture
def training_env_mock():
    """
    Function-scoped fixture for mocked training environment.
    Uses mocked subprocess calls for faster, isolated tests.
    """
    from unittest.mock import MagicMock, patch

    env = TrainingEnvironment()

    def mock_subprocess_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        return mock_result

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        yield env


@pytest.fixture
def mock_faucet_response():
    """Mock faucet API response for testing"""
    return {
        "status": "success",
        "address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
        "amount": 1000,
        "transaction_id": "tx_test123",
        "timestamp": "2026-05-05T12:00:00",
    }


# ---------------------------------------------------------------------------
# fakeredis fixtures — in-process Redis fakes (no server required)
# Added in v0.5.19 so Redis-dependent tests can run without a live Redis.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def fakeredis_client():
    """A synchronous in-process Redis fake (no server required).

    Uses ``fakeredis.FakeRedis``. Each test gets a fresh, isolated server so
    state never leaks between tests.
    """
    import fakeredis

    client = fakeredis.FakeRedis(version=7, decode_responses=True)
    yield client
    client.flushall()


@pytest.fixture(scope="function")
async def fakeredis_async_client():
    """An asynchronous in-process Redis fake (no server required).

    Uses ``fakeredis.FakeAsyncRedis``. Each test gets a fresh, isolated server
    so state never leaks between tests.
    """
    import fakeredis

    client = fakeredis.FakeAsyncRedis(version=7, decode_responses=True)
    yield client
    await client.aclose()
