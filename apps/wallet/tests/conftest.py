"""Wallet daemon test configuration"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

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
