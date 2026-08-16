from __future__ import annotations

import atexit
import os
import shutil
import socket
import tempfile

import pytest

# Keep chain databases out of the deployed data directory. The repo-root conftest already
# does this for a full run, but this suite is also run on its own from apps/blockchain-node,
# where that file is not collected — and on its own is how it created `chain-a/` and
# `chain-sig/` under /var/lib/aitbc/data, named after the test-only chain IDs below (V23-73).
# `setdefault`, so the root conftest's directory wins when both are in play.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="aitbc-chain-tests-data-")
atexit.register(shutil.rmtree, _TEST_DATA_DIR, True)
os.makedirs(os.path.join(_TEST_DATA_DIR, "data"), exist_ok=True)
os.environ.setdefault("AITBC_DATA_DIR", _TEST_DATA_DIR)

# Disable rate limiting in tests to avoid 429s from tight loops
os.environ.setdefault("AITBC_ENABLE_RATE_LIMITING", "false")
# Enable multi-validator consensus for tests (threshold guard bypass)
os.environ.setdefault("MULTI_VALIDATOR_CONSENSUS_ENABLED", "true")

from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block, Receipt, Transaction  # noqa: F401 - ensure models imported for metadata
from sqlmodel import Session, create_engine


# Chain IDs used by isolated blockchain-node tests. AITBC's real chain whitelist
# lives in settings, but unit tests spin up throwaway chains; this fixture makes
# those chains valid for validate_chain_id() without touching production config.
_TEST_CHAIN_IDS = {
    "test-chain",
    "test",
    "chain-a",
    "chain-b",
    "chain-c",
    "chain-empty",
    "chain-sig",
    "secondary",
    "default-chain",
    "ait-testnet",
    "ait-mainnet",
}


@pytest.fixture(autouse=True)
def _allow_test_chain_ids(monkeypatch) -> None:
    """Add the test chain IDs to supported_chains for the duration of each test."""
    existing = {c.strip() for c in settings.supported_chains.split(",") if c.strip()}
    supported = ",".join(sorted(existing | _TEST_CHAIN_IDS))
    monkeypatch.setattr(settings, "supported_chains", supported)


# A `pytest_runtest_setup` hook used to sit here. It walked SQLModel's global metadata before
# every test in this directory and removed each table that did not belong to `aitbc_chain`,
# because this suite's fixtures called `SQLModel.metadata.create_all` and would otherwise have
# built coordinator-api's schema into a blockchain test's database.
#
# The cost was out of all proportion to that. `MetaData.remove` is permanent: a class registers
# its `Table` when its module first executes, and the module then stays in `sys.modules`, so
# nothing ever put those tables back. Every suite collected after this one ran with a registry
# this hook had emptied -- which is what left six coordinator-api test files failing on "no
# such table: users" while passing in isolation (V23-71b).
#
# `aitbc_chain` now owns its tables on `chain_metadata`, so the fixtures name that registry and
# there is nothing to keep out (V23-74).

# ---------------------------------------------------------------------------
# Auto-skip infrastructure-dependent tests when the resource is unreachable.
# Uses pytest_collection_modifyitems so the check runs once per session (not
# per-test), keeping collection fast.
# ---------------------------------------------------------------------------

_REDIS_AVAILABLE: bool | None = None
_POSTGRES_AVAILABLE: bool | None = None


def _check_redis() -> bool:
    """Fast TCP probe to the Redis host/port from REDIS_URL (default localhost:6379)."""
    global _REDIS_AVAILABLE
    if _REDIS_AVAILABLE is not None:
        return _REDIS_AVAILABLE
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    # Parse host/port from redis://host:port/db or rediss://... or unix://...
    try:
        if "://" not in url:
            _REDIS_AVAILABLE = False
            return False
        scheme, rest = url.split("://", 1)
        if scheme == "unix":
            path = rest.split("?", 0)[0]
            _REDIS_AVAILABLE = os.path.exists(path)
            return _REDIS_AVAILABLE
        # redis:// or rediss:// — extract host:port
        host_part = rest.split("/", 0)[0].split("?", 0)[0]
        if "@" in host_part:
            host_part = host_part.split("@", 1)[1]
        host, _, port_str = host_part.partition(":")
        port = int(port_str) if port_str else 6379
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect((host or "localhost", port))
            _REDIS_AVAILABLE = True
        except OSError:
            _REDIS_AVAILABLE = False
        finally:
            s.close()
    except Exception:
        _REDIS_AVAILABLE = False
    return _REDIS_AVAILABLE


def _check_postgres() -> bool:
    """Fast TCP probe to the Postgres host/port from DATABASE_URL / MEMPOOL_DB_URL."""
    global _POSTGRES_AVAILABLE
    if _POSTGRES_AVAILABLE is not None:
        return _POSTGRES_AVAILABLE
    # Try the most likely env vars; default to localhost:5432
    url = os.environ.get("DATABASE_URL") or os.environ.get("MEMPOOL_DB_URL") or "postgresql://localhost:5432/aitbc"
    try:
        if "://" not in url:
            _POSTGRES_AVAILABLE = False
            return False
        _scheme, rest = url.split("://", 1)
        host_part = rest.split("/", 0)[0].split("?", 0)[0]
        if "@" in host_part:
            host_part = host_part.split("@", 1)[1]
        host, _, port_str = host_part.partition(":")
        port = int(port_str) if port_str else 5432
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect((host or "localhost", port))
            _POSTGRES_AVAILABLE = True
        except OSError:
            _POSTGRES_AVAILABLE = False
        finally:
            s.close()
    except Exception:
        _POSTGRES_AVAILABLE = False
    return _POSTGRES_AVAILABLE


def _check_genesis(chain_id: str | None = None) -> bool:
    """Check whether a genesis file exists on disk for the given chain."""
    from aitbc.constants import REPO_DIR

    cid = chain_id or os.environ.get("CHAIN_ID", "test-chain")
    # Common genesis locations
    candidates = [
        REPO_DIR / "apps" / "blockchain-node" / "data" / cid / "genesis.json",
        REPO_DIR / "data" / cid / "genesis.json",
        REPO_DIR / "apps" / "blockchain-node" / "genesis.json",
    ]
    # Also check the production data dir
    prod = os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data")
    candidates.append(__import__("pathlib").Path(prod) / cid / "genesis.json")
    return any(p.exists() for p in candidates)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-skip tests marked requires_redis / requires_postgres / requires_genesis
    when the corresponding resource is not available."""
    redis_ok = _check_redis()
    postgres_ok = _check_postgres()

    for item in items:
        if "requires_redis" in item.keywords and not redis_ok:
            item.add_marker(pytest.mark.skip(reason="Redis not available"))
        if "requires_postgres" in item.keywords and not postgres_ok:
            item.add_marker(pytest.mark.skip(reason="PostgreSQL not available"))
        if "requires_genesis" in item.keywords and not _check_genesis():
            item.add_marker(pytest.mark.skip(reason="Genesis file not available"))


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        chain_metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session
        session.rollback()
