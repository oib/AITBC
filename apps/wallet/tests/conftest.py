"""Wallet daemon test configuration"""

from __future__ import annotations

import atexit
import gc
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Everything below runs at conftest import — before any test module in this
# directory is collected and before the first wallet_app/aitbc import, which is
# the only ordering that matters: aitbc.constants freezes DATA_DIR/CONFIG_DIR/
# LOG_DIR at import, wallet_app.settings instantiates Settings() at import, and
# ApiKeyStorage.__init__ creates its filelock wherever API_KEY_STORAGE_PATH
# points. A session fixture would be far too late for any of that.

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="aitbc-wallet-tests-"))
atexit.register(shutil.rmtree, _TEST_ROOT, True)


def _is_test_scratch(path: object) -> bool:
    """True for paths under <tmp>/aitbc-* — this suite's root or the repo
    conftest's aitbc-tests-data- dir."""
    try:
        resolved = str(Path(str(path)).resolve())
    except (TypeError, ValueError):
        return False
    return resolved.startswith(str(Path(tempfile.gettempdir()).resolve()) + os.sep + "aitbc-")


def _assert_no_early_bindings() -> None:
    """In a combined multi-suite run, another conftest or an earlier-collected
    suite may have imported the path-binding modules before this file ran.
    A collection error here beats tests silently pointing at live data."""
    problems: list[str] = []
    constants = sys.modules.get("aitbc.constants")
    if constants is not None:
        for name in ("DATA_DIR", "CONFIG_DIR", "LOG_DIR"):
            bound = getattr(constants, name, None)
            if bound is not None and not _is_test_scratch(bound):
                problems.append(f"aitbc.constants.{name} = {bound}")
    if "wallet_app.settings" in sys.modules:
        problems.append("wallet_app.settings already imported — its Settings() read the ambient env")
    api_key_mod = sys.modules.get("aitbc.auth.api_key")
    if api_key_mod is not None:
        storage_cls = getattr(api_key_mod, "ApiKeyStorage", ())
        for obj in gc.get_objects():
            if isinstance(obj, storage_cls) and not _is_test_scratch(getattr(obj, "storage_path", "")):
                problems.append(f"ApiKeyStorage already bound to {obj.storage_path}")
    if problems:
        raise RuntimeError(
            "wallet tests cannot isolate the environment — bindings were made before this conftest ran: " + "; ".join(problems)
        )


_assert_no_early_bindings()

# Scrub ambient values Settings()/ServiceSettings()/DatabaseConfig() parse from
# the environment at import — a dev box's DEBUG=release or a node env's PORT
# either breaks validation at collection or quietly steers tests at live state.
for _env_name in (
    "APP_NAME",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "ENVIRONMENT",
    "NODE_ENV",
    "DEBUG",
    "SERVICE_NAME",
    "LOG_LEVEL",
    "LOG_DIR",
    "API_PREFIX",
    "ENABLE_METRICS",
    "ENABLE_HEALTH_CHECK",
    "HOST",
    "PORT",
    "REST_PREFIX",
    "WALLET_API_KEY",
    "WALLET_AUTH_ENABLED",
    "COORDINATOR_BASE_URL",
    "BLOCKCHAIN_RPC_URL",
    "DATABASE",
    "DATABASE_URL",
    "DATABASE_ADAPTER",
    "ADAPTER",
    "URL",
    "DB_FILENAME",
    "POOL_SIZE",
    "MAX_OVERFLOW",
    "POOL_PRE_PING",
    "AITBC_HOME",  # would re-point every constants default at the checkout
):
    os.environ.pop(_env_name, None)

# Isolating vars are force-assigned, not setdefault — an ambient path is the
# leak being removed, so it never gets to win. AITBC_DATA_DIR is the data
# ROOT: services append "data/" themselves (DATA_DIR/data/<svc>.db), so it
# points at _TEST_ROOT — not _TEST_ROOT/data, which would produce the
# never-created data/data/ level the combined critical gate hit.
os.environ["AITBC_DATA_DIR"] = str(_TEST_ROOT)
os.environ["AITBC_CONFIG_DIR"] = str(_TEST_ROOT / "config")
os.environ["AITBC_LOG_DIR"] = str(_TEST_ROOT / "logs")
os.environ["API_KEY_STORAGE_PATH"] = str(_TEST_ROOT / "api_keys.json")
for _dir in ("data", "config", "logs"):
    (_TEST_ROOT / _dir).mkdir(parents=True, exist_ok=True)

# wallet_app.settings instantiates Settings() at import time and COORDINATOR_API_KEY is
# required with no default, so it has to be present before the first wallet_app import.
os.environ.setdefault("COORDINATOR_API_KEY", "test-coordinator-key")

from wallet_app.crypto.encryption import EncryptionSuite  # noqa: E402
from wallet_app.keystore.persistent_service import PersistentKeystoreService  # noqa: E402

# Satisfies validate_password_rules: >=12 chars, upper, lower, digit, symbol.
TEST_PASSWORD = "Correct-Horse-9!"
OTHER_PASSWORD = "Battery-Staple-7!"


@pytest.fixture
def keystore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[PersistentKeystoreService]:
    """A keystore backed by a throwaway SQLite file, with chain registration stubbed out.

    `create_wallet` posts to the blockchain RPC to register the address. That call already
    degrades gracefully on failure, but stubbing it keeps these tests offline and fast
    rather than waiting on a 10s httpx timeout per created wallet.

    The service rejects any db_path outside the CWD (directory-traversal guard), so the
    tmp dir is made the CWD rather than weakening the guard for tests.
    """
    monkeypatch.setattr(
        PersistentKeystoreService,
        "_register_account_on_chain",
        lambda self, address: {"success": False, "created": False, "message": "stubbed", "balance": 0},
    )
    monkeypatch.chdir(tmp_path)
    yield PersistentKeystoreService(db_path=tmp_path / "keystore.db")


@pytest.fixture
def encryption() -> EncryptionSuite:
    return EncryptionSuite()
