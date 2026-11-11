"""#1740 pins: unrecoverable chain.db write errors quarantine the store.

Round-2 of the v12 disk-full drill: ``sqlite3.OperationalError: database or
disk is full`` (SQLITE_FULL) bypassed the #1265 integrity quarantine —
``PRAGMA quick_check`` still passes on a full-but-unimpaired file, so the
node retried imports every ~15 s forever while /ready reported ready and
/v1/height served stale 200s. Now the error shape itself quarantines through
the same gates, and the sweep's writability probe — not quick_check alone —
decides when the store may serve again.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from aitbc_chain.config import settings
from aitbc_chain.database import (
    _probe_chain_db_writable,
    chain_db_quarantine_reason,
    clear_chain_db_quarantine,
    classify_unrecoverable_db_error,
    ensure_chain_db_healthy,
    init_db,
    is_chain_db_quarantined,
    quarantine_chain_db_for_error,
    shutdown_db,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block
from aitbc_chain.sync import ChainSync

CHAIN = "quarantine-1740"


def _unique_chain() -> str:
    return f"q1740-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _clean_quarantine():
    clear_chain_db_quarantine()
    yield
    clear_chain_db_quarantine()


def _file_engine(tmp_path: Path, name: str = "chain.db"):
    path = tmp_path / name
    engine = create_engine(f"sqlite:///{path}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _real_sqlite_full() -> sqlite3.OperationalError:
    """A genuine SQLITE_FULL — ``PRAGMA max_page_count`` makes sqlite itself
    raise 'database or disk is full' with sqlite_errorcode=13."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA max_page_count = 8")
    conn.execute("CREATE TABLE t(x)")
    try:
        conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(5000)])
        conn.commit()
    except sqlite3.OperationalError as exc:
        conn.close()
        return exc
    conn.close()
    raise AssertionError("expected SQLITE_FULL was not raised")


def _sa_wrapped(exc: BaseException) -> SAOperationalError:
    """Wrap a DBAPI error the way SQLAlchemy does at the commit boundary."""
    return SAOperationalError("INSERT INTO block ...", {}, exc)


# ── classification ────────────────────────────────────────────────


def test_classify_real_sqlite_full():
    detail = classify_unrecoverable_db_error(_sa_wrapped(_real_sqlite_full()))
    assert detail is not None
    assert "SQLITE_FULL" in detail or "disk is full" in detail


def test_classify_extended_ioerr_code():
    """Extended result codes mask to their primary byte (IOERR_WRITE etc.)."""

    class _FakeSqliteErr(Exception):
        sqlite_errorcode = 10 | (1 << 8)  # SQLITE_IOERR_WRITE extended form
        sqlite_errorname = "SQLITE_IOERR_WRITE"

    assert classify_unrecoverable_db_error(_FakeSqliteErr("disk I/O error")) is not None


def test_classify_message_fallbacks():
    assert classify_unrecoverable_db_error(Exception("database or disk is full")) is not None
    assert classify_unrecoverable_db_error(OSError(28, "No space left on device")) is not None
    assert classify_unrecoverable_db_error(Exception("database disk image is malformed")) is not None


def test_transient_and_data_errors_are_not_quarantine_class():
    assert classify_unrecoverable_db_error(sqlite3.OperationalError("database is locked")) is None
    assert classify_unrecoverable_db_error(sqlite3.OperationalError("database is busy")) is None
    assert classify_unrecoverable_db_error(sqlite3.IntegrityError("UNIQUE constraint failed: block.hash")) is None
    assert classify_unrecoverable_db_error(ValueError("not a db error")) is None
    assert classify_unrecoverable_db_error(None) is None


# ── quarantine + recovery ─────────────────────────────────────────


def test_write_error_quarantines_and_ensure_refuses(tmp_path):
    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    try:
        reason = quarantine_chain_db_for_error(chain, _sa_wrapped(_real_sqlite_full()), engine=engine)
        assert reason is not None
        assert is_chain_db_quarantined(chain)
        assert "write failure" in (chain_db_quarantine_reason(chain) or "")
        ok, why = ensure_chain_db_healthy(chain, engine=engine)
        assert ok is False
        assert "quarantined" in why
    finally:
        engine.dispose()


def test_force_reverify_clears_when_store_is_writable_again(tmp_path):
    """Disk freed → the sweep's probe passes → quarantine lifts."""
    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    try:
        quarantine_chain_db_for_error(chain, _sa_wrapped(_real_sqlite_full()), engine=engine)
        assert is_chain_db_quarantined(chain)
        ok, detail = ensure_chain_db_healthy(chain, engine=engine, force=True)
        assert (ok, detail) == (True, "ok")
        assert not is_chain_db_quarantined(chain)
    finally:
        engine.dispose()


def test_force_reverify_keeps_quarantine_while_writes_still_fail(tmp_path, monkeypatch):
    """quick_check stays green on a full-but-unimpaired file — only the
    writability probe may lift the quarantine, and it must fail while the
    store still cannot accept writes."""
    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    try:
        quarantine_chain_db_for_error(chain, _sa_wrapped(_real_sqlite_full()), engine=engine)
        monkeypatch.setattr(
            "aitbc_chain.database._probe_chain_db_writable",
            lambda _engine: (False, "database or disk is full"),
        )
        ok, why = ensure_chain_db_healthy(chain, engine=engine, force=True)
        assert ok is False
        assert "write probe failed" in why
        assert is_chain_db_quarantined(chain)
    finally:
        engine.dispose()


def test_probe_detects_readonly_store(tmp_path):
    """The probe itself classifies a real write failure (chmod 444)."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores permission bits")
    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    try:
        quarantine_chain_db_for_error(chain, _sa_wrapped(_real_sqlite_full()), engine=engine)
        db_file = engine.url.database
        engine.dispose()  # drop pooled fds — chmod only gates new opens
        os.chmod(db_file, 0o444)
        try:
            ok, detail = _probe_chain_db_writable(engine)
            assert ok is False
            assert detail
        finally:
            os.chmod(db_file, 0o644)
    finally:
        engine.dispose()


# ── import path wiring ────────────────────────────────────────────


def _seed_head(engine, chain: str) -> None:
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=chain,
                height=0,
                hash="0x" + "11" * 32,
                parent_hash="0x00",
                proposer="0x" + "22" * 20,
                timestamp=datetime.now(UTC),
                tx_count=0,
            )
        )
        session.commit()


def _block_one(chain: str) -> dict:
    return {
        "chain_id": chain,
        "height": 1,
        "hash": "0x" + "33" * 32,
        "parent_hash": "0x" + "11" * 32,
        "proposer": "0x" + "22" * 20,
        "timestamp": datetime.now(UTC).isoformat(),
        "tx_count": 0,
    }


def test_import_block_quarantines_on_disk_full(tmp_path, monkeypatch):
    """The drill's exact shape: append raises OperationalError 'database or
    disk is full' → import is rejected AND the chain is quarantined, so the
    next attempt refuses at the health gate instead of retrying forever."""
    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    _seed_head(engine, chain)
    factory = sessionmaker(engine, class_=Session)
    sync = ChainSync(factory, chain_id=chain, validate_signatures=False)
    calls = {"n": 0}

    def _append_full(*_args, **_kwargs):
        calls["n"] += 1
        raise _sa_wrapped(_real_sqlite_full())

    monkeypatch.setattr(sync, "_append_block", _append_full)
    try:
        result = sync.import_block(_block_one(chain), transactions=[])
        assert result.accepted is False
        assert "quarantined" in (result.reason or "")
        assert is_chain_db_quarantined(chain)

        # Second attempt must refuse at ensure_chain_db_healthy — _append_block
        # is never reached again.
        result2 = sync.import_block(_block_one(chain), transactions=[])
        assert result2.accepted is False
        assert "quarantined" in (result2.reason or "")
        assert calls["n"] == 1
    finally:
        engine.dispose()
        clear_chain_db_quarantine(chain)


def test_import_block_still_rejects_transient_errors_without_quarantine(tmp_path, monkeypatch):
    """'database is locked' is contention, not quarantine-class — the import
    fails but the chain stays healthy."""
    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    _seed_head(engine, chain)
    factory = sessionmaker(engine, class_=Session)
    sync = ChainSync(factory, chain_id=chain, validate_signatures=False)

    def _append_locked(*_args, **_kwargs):
        raise SAOperationalError("INSERT INTO block ...", {}, sqlite3.OperationalError("database is locked"))

    monkeypatch.setattr(sync, "_append_block", _append_locked)
    try:
        result = sync.import_block(_block_one(chain), transactions=[])
        assert result.accepted is False
        assert "locked" in (result.reason or "").lower() or "Append block failed" in (result.reason or "")
        assert not is_chain_db_quarantined(chain)
    finally:
        engine.dispose()
        clear_chain_db_quarantine(chain)


# ── /ready honesty ────────────────────────────────────────────────


def test_ready_check_fails_while_quarantined(tmp_path):
    """_check_chain_db must fail closed on quarantine — SELECT 1 alone kept
    reporting ready on a node that could not write (the drill's 200s)."""
    from aitbc_chain.app import _check_chain_db
    from aitbc_chain.rpc.utils import get_supported_chains

    engine = _file_engine(tmp_path)
    _unique_chain()
    try:
        cid = get_supported_chains()[0] if get_supported_chains() else settings.chain_id
        quarantine_chain_db_for_error(cid, _sa_wrapped(_real_sqlite_full()), engine=engine)
        with pytest.raises(RuntimeError, match="quarantined"):
            _check_chain_db()
    finally:
        engine.dispose()
        clear_chain_db_quarantine()


def test_ready_check_passes_on_healthy_init_db():
    from aitbc_chain.app import _check_chain_db

    init_db()
    try:
        _check_chain_db()  # must not raise
    finally:
        shutdown_db()


# ── #1772: cross-process (split-unit) quarantine visibility ────────


def test_quarantine_marker_survives_in_process_state_loss(tmp_path):
    """#1772: the node unit quarantines on an unrecoverable write error; the
    rpc unit's own ``_corrupted_chains`` stays empty and its quick_check
    still passes. The marker file beside chain.db must keep the store
    reported-quarantined for sibling processes, and only the sweep's
    writability probe may lift it."""
    import aitbc_chain.database as db_mod

    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    try:
        quarantine_chain_db_for_error(chain, _sa_wrapped(_real_sqlite_full()), engine=engine)
        marker = db_mod._quarantine_marker_path(chain)
        assert marker.is_file()

        # Simulate the sibling rpc process: same files on disk, empty
        # in-process quarantine state.
        db_mod._corrupted_chains.pop(chain, None)
        db_mod._corrupted_identities.pop(chain, None)
        assert is_chain_db_quarantined(chain)  # via the marker, not the dict

        # Store writable again → the probe confirm lifts marker + quarantine.
        ok, _detail = ensure_chain_db_healthy(chain, engine=engine, force=True)
        assert ok is True
        assert not marker.exists()
        assert not is_chain_db_quarantined(chain)
    finally:
        engine.dispose()
        clear_chain_db_quarantine(chain)


def test_quarantine_marker_holds_while_writes_still_fail(tmp_path, monkeypatch):
    """#1772: quick_check stays green on a READONLY/full-but-unimpaired
    file — the marker must survive every sweep until the writability
    probe passes, so /ready never flaps back to 200 mid-fault."""
    import aitbc_chain.database as db_mod

    engine = _file_engine(tmp_path)
    chain = _unique_chain()
    try:
        quarantine_chain_db_for_error(chain, _sa_wrapped(_real_sqlite_full()), engine=engine)
        db_mod._corrupted_chains.pop(chain, None)
        db_mod._corrupted_identities.pop(chain, None)
        marker = db_mod._quarantine_marker_path(chain)
        assert marker.is_file()

        monkeypatch.setattr(
            "aitbc_chain.database._probe_chain_db_writable",
            lambda _engine: (False, "database or disk is full"),
        )
        ok, why = ensure_chain_db_healthy(chain, engine=engine, force=True)
        assert ok is False
        assert "write probe failed" in why
        assert marker.is_file()
        assert is_chain_db_quarantined(chain)
    finally:
        engine.dispose()
        clear_chain_db_quarantine(chain)


def test_ready_check_fails_on_foreign_quarantine_marker(tmp_path):
    """#1772 end-to-end: a process that never saw the write error (the rpc
    unit) still fails /ready because the sibling's marker is visible —
    the exact stale-200 shape from the v14(2) drill."""
    import aitbc_chain.database as db_mod
    from aitbc_chain.app import _check_chain_db
    from aitbc_chain.rpc.utils import get_supported_chains

    engine = _file_engine(tmp_path)
    try:
        cid = get_supported_chains()[0] if get_supported_chains() else settings.chain_id
        quarantine_chain_db_for_error(cid, _sa_wrapped(_real_sqlite_full()), engine=engine)
        # Sibling-process view: no in-process record, marker only.
        db_mod._corrupted_chains.pop(cid, None)
        db_mod._corrupted_identities.pop(cid, None)
        assert is_chain_db_quarantined(cid)
        with pytest.raises(RuntimeError, match="quarantined"):
            _check_chain_db()
    finally:
        engine.dispose()
        clear_chain_db_quarantine()
