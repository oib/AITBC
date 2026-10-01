"""The keeper connection: one idle SQLite connection per chain, opt-in.

Without it every session opens and closes its own connection (NullPool), and the session that
closes last checkpoints and deletes the WAL under an EXCLUSIVE lock while it syncs the disk. On a
disk with slow fsync that lock is held for seconds, and every connection opened meanwhile fails
after the 5 s default wait with "database is locked" (node2, 2026-10-01: an attestation check at
height 30415 and several propose attempts). A keeper means no session is ever the last one, so the
WAL is only checkpointed passively and the exclusive lock is never taken.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from aitbc_chain import database
from aitbc_chain.config import settings
from aitbc_chain.database import init_db, session_scope, shutdown_db


@pytest.fixture
def chain():
    """A throwaway chain id, shut down (keeper included) after the test."""
    chain_id = "keeper-test-chain"
    yield chain_id
    shutdown_db(chain_id)


def _wal(chain_id: str) -> Path:
    path = settings.get_db_path(chain_id)
    return path.with_name(path.name + "-wal")


def _write_session(chain_id: str) -> None:
    """One short session that commits a write, like any proposer or sync session does."""
    with session_scope(chain_id) as session:
        session.execute(text("CREATE TABLE IF NOT EXISTS keeper_probe (a INTEGER)"))
        session.execute(text("INSERT INTO keeper_probe VALUES (1)"))
        session.commit()


def test_off_by_default() -> None:
    assert settings.db_keeper_connection is False


def test_without_a_keeper_closing_the_last_session_deletes_the_wal(chain, monkeypatch) -> None:
    """The behaviour the keeper exists to avoid: every quiet moment ends in a checkpoint and a
    WAL delete, which on a slow disk is an exclusive lock held for seconds."""
    monkeypatch.setattr(settings, "db_keeper_connection", False)
    init_db(chain)
    _write_session(chain)
    assert chain not in database._keepers
    assert not _wal(chain).exists()


def test_with_a_keeper_the_wal_survives_the_last_session(chain, monkeypatch) -> None:
    monkeypatch.setattr(settings, "db_keeper_connection", True)
    init_db(chain)
    assert chain in database._keepers
    _write_session(chain)
    assert _wal(chain).exists(), "a session closing must not checkpoint and delete the WAL while a keeper is open"
    _write_session(chain)
    assert _wal(chain).exists()


def test_init_db_twice_holds_one_keeper(chain, monkeypatch) -> None:
    """init_db runs again for a chain (sync manager, on-demand RPC): still one connection."""
    monkeypatch.setattr(settings, "db_keeper_connection", True)
    init_db(chain)
    first = database._keepers[chain]
    init_db(chain)
    assert database._keepers[chain] is first
    assert len(database._keepers) == 1


def test_shutdown_releases_the_keeper(chain, monkeypatch) -> None:
    monkeypatch.setattr(settings, "db_keeper_connection", True)
    init_db(chain)
    assert chain in database._keepers
    _write_session(chain)
    shutdown_db(chain)
    assert chain not in database._keepers
    # The keeper was the last connection, so closing it does the one checkpoint-and-delete.
    assert not _wal(chain).exists()


def test_keeper_survives_a_session_error(chain, monkeypatch) -> None:
    """A session that fails mid-transaction must not take the keeper down with it."""
    monkeypatch.setattr(settings, "db_keeper_connection", True)
    init_db(chain)
    with pytest.raises(OperationalError):
        with session_scope(chain) as session:
            session.execute(text("SELECT * FROM table_that_does_not_exist"))
    assert chain in database._keepers
    _write_session(chain)
    assert _wal(chain).exists()


def test_failing_to_open_the_keeper_never_stops_startup(monkeypatch, caplog) -> None:
    """The keeper is an optimisation: if it cannot be opened the node starts without it."""

    class _BrokenEngine:
        def raw_connection(self):
            raise OperationalError("PRAGMA journal_mode=WAL", {}, Exception("database is locked"))

    monkeypatch.setattr(settings, "db_keeper_connection", True)
    with caplog.at_level(logging.WARNING):
        database._hold_keeper_connection("broken-chain", _BrokenEngine())  # type: ignore[arg-type]
    assert "broken-chain" not in database._keepers
    assert any("keeper connection" in r.message for r in caplog.records)
