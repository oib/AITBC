"""DATA-LAYOUT: ``BRIDGE_DEPOSITS_DB`` env override resolves identically in
every consumer of the bridge ledger, and every consumer falls back to the
*same* default it used before the override existed.

The ledger is a shared multi-consumer database. If one consumer misses the
override during a later migration it silently recreates an empty ledger at
the old path (``sqlite3.connect()`` creates the file) — split-brain with no
error. This table is the single list DATA-LAYOUT-2 edits when the default
flips to ``DATA_DIR/data/bridge_deposits.db``.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `aitbc` (constants, logging) is imported by the exchange handler. The
# repo-root conftest already puts blockchain-node/src on sys.path; doing it
# here too keeps this module runnable standalone.
_AITBC_SRC = str(REPO_ROOT / "apps" / "blockchain-node" / "src")
if _AITBC_SRC not in sys.path:
    sys.path.insert(0, _AITBC_SRC)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ENV_VAR = "BRIDGE_DEPOSITS_DB"
DEFAULT_NAME = "bridge_deposits.db"


def _load_standalone(name: str, rel_path: str):
    """Exec a stdlib-only module straight from the file under test.

    Deliberately bypasses any editable install — from a worktree,
    ``import wallet_app`` would resolve to the primary checkout and the
    test would pass against a tree that is not the one being changed.
    """
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _exchange_resolved_path(monkeypatch, env_path: str | None, data_dir: str | None) -> str:
    """Capture the ledger path ``_check_bridge_storage`` actually opens."""
    from apps.exchange.simple_exchange.handlers import exchange

    if env_path is None:
        monkeypatch.delenv(ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_VAR, env_path)
    if data_dir is not None:
        import aitbc.constants

        monkeypatch.setattr(aitbc.constants, "DATA_DIR", data_dir)

    captured: dict[str, str] = {}
    real_connect = sqlite3.connect

    def spy(path, *args, **kwargs):
        captured["path"] = str(path)
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(exchange, "sqlite3", SimpleNamespace(connect=spy))
    exchange._check_bridge_storage()
    return captured["path"]


def _mk_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE eth_deposits (id INTEGER)")
        conn.commit()
    finally:
        conn.close()


@dataclass(frozen=True)
class Consumer:
    """One bridge-ledger consumer and how it resolves the path.

    kind "module": file exec exposes ``DB_PATH`` (import-time resolution).
    kind "exchange": ``_check_bridge_storage`` resolves at call time and is
    captured via a ``sqlite3.connect`` spy.
    """

    label: str
    rel_path: str
    kind: str


# The complete consumer table. Add a row for every new code path that opens
# the ledger; DATA-LAYOUT-2 flips the expected default here.
CONSUMERS = [
    Consumer("bridge_monitor.storage.DB_PATH", "apps/bridge-monitor/src/bridge_monitor/storage.py", "module"),
    Consumer("wallet_app.bridge.bridge_db.DB_PATH", "apps/wallet/src/wallet_app/bridge/bridge_db.py", "module"),
    Consumer(
        "exchange._check_bridge_storage",
        "apps/exchange/simple_exchange/handlers/exchange.py",
        "exchange",
    ),
]


def _resolve(consumer: Consumer, monkeypatch: pytest.MonkeyPatch, env_path, data_dir) -> str:
    if consumer.kind == "module":
        if env_path is None:
            monkeypatch.delenv(ENV_VAR, raising=False)
        else:
            monkeypatch.setenv(ENV_VAR, env_path)
        monkeypatch.delenv("AITBC_DATA_DIR", raising=False)
        monkeypatch.delenv("DATA_DIR", raising=False)
        mod = _load_standalone("consumer_under_test", consumer.rel_path)
        return str(mod.DB_PATH)
    return _exchange_resolved_path(monkeypatch, env_path, data_dir)


def test_env_override_resolves_same_path_in_every_consumer(tmp_path, monkeypatch):
    override = tmp_path / "scratch" / "ledger.db"
    _mk_ledger(override)
    for c in CONSUMERS:
        assert _resolve(c, monkeypatch, str(override), None) == str(override), c.label


def test_unset_env_resolves_existing_default(tmp_path, monkeypatch):
    # exchange resolves through aitbc.constants.DATA_DIR (patched); the two
    # module consumers resolve AITBC_DATA_DIR/DATA_DIR/default at exec time
    # — cleared above — so their default is /var/lib/aitbc/<name>. Pin both
    # to their respective current defaults and assert identity.
    ex_dir = tmp_path / "exdata"
    _mk_ledger(ex_dir / DEFAULT_NAME)
    for c in CONSUMERS:
        resolved = _resolve(c, monkeypatch, None, str(ex_dir))
        if c.kind == "exchange":
            assert resolved == str(ex_dir / DEFAULT_NAME), c.label
        else:
            assert resolved == os.path.join("/var/lib/aitbc", DEFAULT_NAME), c.label


@pytest.mark.parametrize("blank", ["", "   ", " \t "])
def test_blank_env_is_treated_as_unset(tmp_path, monkeypatch, blank):
    """A bare ``BRIDGE_DEPOSITS_DB=`` (or whitespace) in an EnvironmentFile
    must not reach ``sqlite3.connect('')`` — that opens a private temporary
    database, a split-brain with no error. Blank is unset."""
    ex_dir = tmp_path / "exdata-blank"
    _mk_ledger(ex_dir / DEFAULT_NAME)
    for c in CONSUMERS:
        resolved = _resolve(c, monkeypatch, blank, str(ex_dir))
        if c.kind == "exchange":
            assert resolved == str(ex_dir / DEFAULT_NAME), c.label
        else:
            assert resolved == os.path.join("/var/lib/aitbc", DEFAULT_NAME), c.label


def test_unset_default_is_unchanged_from_pre_override_layout(tmp_path, monkeypatch):
    """The pre-override default for every consumer was
    ``<data dir>/bridge_deposits.db`` — top-level, not under ``data/``.
    DATA-LAYOUT-2 updates this expectation when the default flips."""
    module_default = os.path.join("/var/lib/aitbc", DEFAULT_NAME)
    for c in CONSUMERS:
        if c.kind == "module":
            assert _resolve(c, monkeypatch, None, None) == module_default, c.label
    # exchange: assert it joins DATA_DIR directly, not DATA_DIR/"data".
    ex_dir = tmp_path / "exdata2"
    _mk_ledger(ex_dir / DEFAULT_NAME)
    assert _exchange_resolved_path(monkeypatch, None, str(ex_dir)) == str(ex_dir / DEFAULT_NAME)
