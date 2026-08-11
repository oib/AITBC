"""
Minimal conftest for pytest discovery
Imports fixtures from dedicated fixture files for better organization
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Register a custom datetime adapter for sqlite3 to suppress the Python 3.12+
# deprecation warning about the default datetime adapter. SQLAlchemy uses
# sqlite3 under the hood for test databases.
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())

# Add coordinator-api src to path for tests that import coordinator_api.main
_COORD_SRC = str(Path(__file__).resolve().parent.parent / "apps" / "coordinator-api" / "src")
if _COORD_SRC not in sys.path:
    sys.path.insert(0, _COORD_SRC)

# Add blockchain-node src to path for tests that import aitbc_chain
_BLOCKCHAIN_SRC = str(Path(__file__).resolve().parent.parent / "apps" / "blockchain-node" / "src")
if _BLOCKCHAIN_SRC not in sys.path:
    sys.path.insert(0, _BLOCKCHAIN_SRC)

# Add miner src to path for tests that import miner_app. The v0.23 remediation commit moved
# this app to a src/ layout and updated apps/miner/pyproject.toml, but not this file, so the
# root suite's tests lost the module while the app's own suite kept it.
_MINER_SRC = str(Path(__file__).resolve().parent.parent / "apps" / "miner" / "src")
if _MINER_SRC not in sys.path:
    sys.path.insert(0, _MINER_SRC)

# Add cli/ to path for tests that import aitbc_cli, for the same reason as the two above --
# and it matters more here. Without it `aitbc_cli` resolves through the editable install,
# which points at the primary checkout, so CLI tests run from a git worktree silently
# exercised a *different tree* than the one under test: edits appeared to have no effect,
# and failures belonged to somebody else's working copy.
_CLI_SRC = str(Path(__file__).resolve().parent.parent / "cli")
if _CLI_SRC not in sys.path:
    sys.path.insert(0, _CLI_SRC)

# NOTE: tests/ is deliberately NOT added to sys.path.
#
# It used to be, "so fixture modules are importable". The side effect was that every
# package directly under tests/ became importable as a top-level name -- and tests/cli/
# has an __init__.py, so `import cli` resolved to the test package rather than the repo's
# cli/ package, for the entire run, and anything importing from the real one got a
# ModuleNotFoundError that pointed nowhere near the cause.
#
# V23-43 removed cli/__init__.py, so there is no longer a `cli` package to shadow -- but the
# reasoning applies to any top-level name tests/ happens to collide with, so tests/ stays off
# the path.
#
# The fixtures are reachable without it: tests/cli/conftest.py puts tests/fixtures itself
# on sys.path, which is what makes `from cli_mocks import ...` work. Nothing imports
# `fixtures.<module>`.

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
