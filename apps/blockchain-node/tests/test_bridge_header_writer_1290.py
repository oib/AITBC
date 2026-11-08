"""#1290 BRIDGE-HEADER-LOSS-1 pins.

node1 dropped bridge header batches because every app-lifespan process
(node RPC workers + island RPC workers) mirrored the same headers into the
same chain.db and losers burned their busy_timeout on "database is locked".

Pinned here:
- ``_bridge_header_writer_lock`` gives exactly one holder per chain at a
  time (second acquire fails while the first is held, succeeds after
  release), and degrades to unlocked when the lock path cannot be resolved.
- ``_run_with_header_lock_retry`` retries sqlite lock errors with backoff
  and re-raises non-lock errors and out-of-budget locks unchanged.
- ``_flush_header_batch`` returns False only after the retry budget, not on
  the first locked error.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc_chain.config import settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata

CHAIN_ID = "chain-a"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    yield engine
    chain_metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def bridge(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(type(settings), "get_db_path", lambda self, chain_id="": tmp_path / f"{chain_id}.db")
    return CrossChainBridge(lambda: Session(engine))


def _sa_lock_error() -> SAOperationalError:
    return SAOperationalError("INSERT", {}, sqlite3.OperationalError("database is locked"))


class TestWriterLock:
    def test_second_holder_is_refused_until_release(self, bridge):
        with bridge._bridge_header_writer_lock(CHAIN_ID) as first:
            assert first is True
            with bridge._bridge_header_writer_lock(CHAIN_ID) as second:
                assert second is False
        with bridge._bridge_header_writer_lock(CHAIN_ID) as third:
            assert third is True

    def test_unresolvable_lock_path_degrades_to_unlocked(self, bridge, monkeypatch):
        def _boom(self, chain_id=""):
            raise RuntimeError("no db path")

        monkeypatch.setattr(type(settings), "get_db_path", _boom)
        with bridge._bridge_header_writer_lock(CHAIN_ID) as acquired:
            assert acquired is True

    def test_sync_skips_when_writer_lock_is_held(self, bridge, engine, monkeypatch):
        """A second process must not mirror headers while another holds the lock."""
        from contextlib import contextmanager

        @contextmanager
        def _held_elsewhere(chain_id):
            yield False

        monkeypatch.setattr(bridge, "_bridge_header_writer_lock", _held_elsewhere)
        assert bridge._sync_local_chain_headers(CHAIN_ID) == 0


class TestLockRetry:
    def test_locked_error_is_retried_then_succeeds(self, bridge, monkeypatch):
        monkeypatch.setattr("aitbc_chain.config.settings.bridge_header_lock_retry_seconds", 30, raising=False)
        calls = {"n": 0}

        def _flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _sa_lock_error()
            return "ok"

        monkeypatch.setattr(bridge, "_HEADER_LOCK_RETRY_BASE_SECONDS", 0.001)
        monkeypatch.setattr(bridge, "_HEADER_LOCK_RETRY_MAX_SECONDS", 0.002)
        assert bridge._run_with_header_lock_retry(_flaky, CHAIN_ID) == "ok"
        assert calls["n"] == 3

    def test_non_lock_error_propagates_without_retry(self, bridge):
        calls = {"n": 0}

        def _bad():
            calls["n"] += 1
            raise ValueError("not a lock")

        with pytest.raises(ValueError):
            bridge._run_with_header_lock_retry(_bad, CHAIN_ID)
        assert calls["n"] == 1

    def test_lock_error_gives_up_after_budget(self, bridge, monkeypatch):
        monkeypatch.setattr("aitbc_chain.config.settings.bridge_header_lock_retry_seconds", 0, raising=False)
        calls = {"n": 0}

        def _always_locked():
            calls["n"] += 1
            raise _sa_lock_error()

        with pytest.raises(SAOperationalError):
            bridge._run_with_header_lock_retry(_always_locked, CHAIN_ID)
        assert calls["n"] == 1

    def test_flush_header_batch_retries_locked_store(self, bridge, monkeypatch):
        monkeypatch.setattr(bridge, "_HEADER_LOCK_RETRY_BASE_SECONDS", 0.001)
        monkeypatch.setattr(bridge, "_HEADER_LOCK_RETRY_MAX_SECONDS", 0.002)
        calls = {"n": 0}

        def _store(chain_id, headers):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _sa_lock_error()
            return len(headers)

        monkeypatch.setattr(bridge, "_store_header_batch", _store)
        pending = [{"chain_id": CHAIN_ID, "height": 1, "hash": "0x" + "01" * 32}]
        assert bridge._flush_header_batch(CHAIN_ID, pending, 1) is True
        assert calls["n"] == 2

    def test_flush_header_batch_still_drops_after_budget(self, bridge, monkeypatch):
        monkeypatch.setattr("aitbc_chain.config.settings.bridge_header_lock_retry_seconds", 0, raising=False)
        monkeypatch.setattr(bridge, "_store_header_batch", MagicMock(side_effect=_sa_lock_error()))
        pending = [{"chain_id": CHAIN_ID, "height": 1, "hash": "0x" + "01" * 32}]
        assert bridge._flush_header_batch(CHAIN_ID, pending, 1) is False
