"""#1615/#1616 pins: chain.db pragma policy — foreign_keys flag and bounded
incremental_vacuum storage maintenance.

- ``settings.db_foreign_keys_enabled`` (default OFF) gates
  ``PRAGMA foreign_keys=ON`` in ``_set_sqlite_pragmas``; when on, an escrow
  row whose buyer/provider has no ``account`` row is refused by SQLite.
- ``settings.db_incremental_vacuum_max_pages`` bounds the per-sweep
  ``PRAGMA incremental_vacuum`` in ``maintain_chain_db_storage``; new
  databases are created with ``auto_vacuum=INCREMENTAL`` so the pass can
  actually return pages (existing auto_vacuum=NONE stores no-op safely).
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from aitbc_chain.config import settings
from aitbc_chain.database import (
    _set_sqlite_pragmas,
    clear_chain_db_quarantine,
    count_foreign_key_violations,
    init_db,
    maintain_chain_db_storage,
    shutdown_db,
)
from aitbc_chain.base_models import Escrow


def _unique_chain() -> str:
    return f"dbpragma-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _clean_state():
    clear_chain_db_quarantine()
    yield
    clear_chain_db_quarantine()


def test_foreign_keys_pragmas_default_off(monkeypatch):
    monkeypatch.setattr(settings, "db_foreign_keys_enabled", False)
    conn = sqlite3.connect(":memory:")
    try:
        _set_sqlite_pragmas(conn, None)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    finally:
        conn.close()


def test_foreign_keys_pragmas_enabled(monkeypatch):
    monkeypatch.setattr(settings, "db_foreign_keys_enabled", True)
    conn = sqlite3.connect(":memory:")
    try:
        _set_sqlite_pragmas(conn, None)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_orphan_escrow_rejected_only_when_flag_on(monkeypatch):
    """Escrow.buyer/provider FK -> account(chain_id, address). With the flag
    on, inserting an escrow for accounts that do not exist fails; off, the
    historical lenient behaviour is preserved."""
    from aitbc_chain.database import session_scope

    for flag, expect_error in ((False, False), (True, True)):
        monkeypatch.setattr(settings, "db_foreign_keys_enabled", flag)
        chain = _unique_chain()
        try:
            init_db(chain)
            with session_scope(chain) as session:
                session.add(
                    Escrow(
                        job_id=f"job-{chain}",
                        chain_id=chain,
                        buyer="0x" + "11" * 20,
                        provider="0x" + "22" * 20,
                        amount=1,
                    )
                )
                if expect_error:
                    with pytest.raises(IntegrityError):
                        session.commit()
                else:
                    session.commit()
        finally:
            shutdown_db(chain)


def test_foreign_key_check_clean_on_fresh_db():
    chain = _unique_chain()
    try:
        init_db(chain)
        from aitbc_chain.database import get_engine

        count, sample = count_foreign_key_violations(get_engine(chain))
        assert count == 0
        assert sample == []
    finally:
        shutdown_db(chain)


def test_new_db_gets_auto_vacuum_incremental():
    """_set_sqlite_pragmas lands before create_all, so a fresh chain.db is
    born with auto_vacuum=INCREMENTAL (header value 2)."""
    chain = _unique_chain()
    try:
        init_db(chain)
        db_path = settings.get_db_path(chain)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        finally:
            conn.close()
    finally:
        shutdown_db(chain)


def test_incremental_vacuum_frees_freelist(monkeypatch):
    """Build a freelist on an INCREMENTAL store, run the sweep helper, and
    confirm bounded reclaim actually returns pages."""
    chain = _unique_chain()
    try:
        init_db(chain)
        from aitbc_chain.database import get_engine

        engine = get_engine(chain)
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS vacuum_probe (a TEXT)"))
            conn.execute(
                text(
                    "INSERT INTO vacuum_probe WITH RECURSIVE cnt(x) AS "
                    "(SELECT 1 UNION ALL SELECT x+1 FROM cnt WHERE x < 8000) "
                    "SELECT 'x' || x FROM cnt"
                )
            )
            conn.commit()
            conn.execute(text("DELETE FROM vacuum_probe"))
            conn.commit()
            freelist_before = int(conn.execute(text("PRAGMA freelist_count")).scalar() or 0)
        assert freelist_before > 0

        monkeypatch.setattr(settings, "db_incremental_vacuum_max_pages", 100000)
        stats = maintain_chain_db_storage(chain)
        assert stats["freelist_count"] == freelist_before
        assert stats["freelist_after"] < freelist_before

        # Bounded: a tiny budget frees at most that many pages.
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM vacuum_probe"))
            conn.execute(
                text(
                    "INSERT INTO vacuum_probe WITH RECURSIVE cnt(x) AS "
                    "(SELECT 1 UNION ALL SELECT x+1 FROM cnt WHERE x < 4000) "
                    "SELECT 'z' || x FROM cnt"
                )
            )
            conn.commit()
            conn.execute(text("DELETE FROM vacuum_probe"))
            conn.commit()
            freelist2 = int(conn.execute(text("PRAGMA freelist_count")).scalar() or 0)
        monkeypatch.setattr(settings, "db_incremental_vacuum_max_pages", 3)
        stats2 = maintain_chain_db_storage(chain)
        assert stats2["freelist_count"] == freelist2
        assert stats2["freelist_after"] >= freelist2 - 3
    finally:
        shutdown_db(chain)


def test_incremental_vacuum_disabled_by_zero(monkeypatch):
    chain = _unique_chain()
    try:
        init_db(chain)
        monkeypatch.setattr(settings, "db_incremental_vacuum_max_pages", 0)
        stats = maintain_chain_db_storage(chain)
        assert "freelist_after" not in stats
        assert "page_count" in stats and "freelist_count" in stats
    finally:
        shutdown_db(chain)
