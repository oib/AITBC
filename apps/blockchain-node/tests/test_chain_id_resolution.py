"""RESET-W2B-1: chain-id resolution and the removed ``ait-mainnet`` fallback.

The autouse conftest fixture pins ``settings.chain_id`` to ``"ait-mainnet"``
(an explicit test-only default), so the unset-case tests below must
monkeypatch it back to ``""`` to simulate an unconfigured node.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from aitbc_chain import database
from aitbc_chain.chain_id import ChainIdNotConfigured, resolve_chain_id
from aitbc_chain.config import settings
from aitbc_chain.database import get_engine, init_db
from aitbc_chain.rpc.utils import _check_request_freshness, get_chain_id


@pytest.fixture
def unconfigured(monkeypatch, tmp_path):
    """Simulate a node with no chain id anywhere, and keep DB state isolated."""
    monkeypatch.setattr(settings, "chain_id", "")
    monkeypatch.setattr(settings, "supported_chains", "")
    monkeypatch.setattr(database, "_default_chain_id", "")
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    yield tmp_path


def test_resolve_prefers_explicit_arg(unconfigured):
    assert resolve_chain_id("explicit-chain") == "explicit-chain"


def test_resolve_prefers_default_over_settings(unconfigured, monkeypatch):
    monkeypatch.setattr(database, "_default_chain_id", "default-chain")
    monkeypatch.setattr(settings, "chain_id", "settings-chain")
    assert resolve_chain_id() == "default-chain"


def test_resolve_uses_settings(unconfigured, monkeypatch):
    monkeypatch.setattr(settings, "chain_id", "settings-chain")
    assert resolve_chain_id() == "settings-chain"


def test_resolve_raises_when_unconfigured(unconfigured):
    with pytest.raises(ChainIdNotConfigured):
        resolve_chain_id()
    with pytest.raises(ChainIdNotConfigured):
        get_chain_id(None)


def test_get_engine_opens_no_file_when_unconfigured(unconfigured, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        type(settings),
        "get_db_path",
        lambda self, chain_id="": calls.append(chain_id) or Path("/nonexistent/chain.db"),
    )
    with pytest.raises(ChainIdNotConfigured):
        get_engine()
    assert calls == []  # resolution failed before any path was consulted
    assert database._engines == {}


def test_init_db_refuses_before_creating_anything(unconfigured, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        type(settings),
        "get_db_path",
        lambda self, chain_id="": calls.append(chain_id) or Path("/nonexistent/chain.db"),
    )
    with pytest.raises(ChainIdNotConfigured):
        init_db()
    assert calls == []
    assert list(unconfigured.iterdir()) == []  # no data dir contents created


def test_app_startup_refuses_unconfigured(unconfigured, monkeypatch):
    """A node with no chain id fails in lifespan before touching a DB path."""
    from fastapi.testclient import TestClient

    from aitbc_chain.app import create_app

    calls: list[str] = []
    monkeypatch.setattr(
        type(settings),
        "get_db_path",
        lambda self, chain_id="": calls.append(chain_id) or Path("/nonexistent/chain.db"),
    )
    app = create_app()
    with pytest.raises(ChainIdNotConfigured):
        with TestClient(app):
            pass
    assert calls == []


def test_admin_replay_guard_fails_closed_unconfigured(unconfigured):
    import time

    payload = {"issued_at": time.time(), "target_chain_id": "anything", "nonce": "n"}
    # Fresh timestamp so the chain check is reached: no configured chain ->
    # the guard cannot prove it is the target and must refuse.
    assert _check_request_freshness(payload) is False


def test_bridge_lock_chain_resolution_raises(unconfigured):
    """The bridge-lock verification path surfaces the typed error (-> 503)."""
    with pytest.raises(ChainIdNotConfigured):
        get_chain_id(None)


def test_chain_id_error_maps_to_503(unconfigured):
    from aitbc_chain.app import create_app

    app = create_app()
    assert ChainIdNotConfigured in app.exception_handlers


class TestSQLCipherGate:
    """Encryption is keyed on the flag plus the key file, not a chain literal."""

    @pytest.fixture(autouse=True)
    def _clean_engines(self, monkeypatch, tmp_path):
        monkeypatch.setattr(database, "_engines", {})
        monkeypatch.setattr(
            type(settings),
            "get_db_path",
            lambda self, chain_id="": tmp_path / f"{chain_id or 'x'}.db",
        )

    def test_flag_off_no_encryption_any_id(self, monkeypatch):
        monkeypatch.setattr(settings, "db_encryption_enabled", False)
        engine = get_engine("test-chain")
        assert engine.dialect.dbapi.__name__ == "sqlite3.dbapi2"

    def test_flag_on_with_keyfile_encrypts_non_mainnet_id(self, monkeypatch, tmp_path):
        key_file = tmp_path / "enc.key"
        key_file.write_bytes(b"k" * 32)
        monkeypatch.setattr(settings, "db_encryption_enabled", True)
        monkeypatch.setattr(settings, "db_encryption_key_path", key_file)
        fake = types.ModuleType("sqlcipher3")
        fake.paramstyle = "qmark"  # dialect reads these at engine construction
        fake.sqlite_version_info = (3, 45, 0)
        monkeypatch.setitem(sys.modules, "sqlcipher3", fake)
        engine = get_engine("test-chain")  # not "ait-mainnet"
        assert engine.dialect.dbapi is fake

    def test_flag_on_missing_keyfile_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "db_encryption_enabled", True)
        monkeypatch.setattr(settings, "db_encryption_key_path", tmp_path / "missing.key")
        engine = get_engine("test-chain")
        assert engine.dialect.dbapi.__name__ == "sqlite3.dbapi2"
