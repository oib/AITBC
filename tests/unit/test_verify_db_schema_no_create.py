"""NO-CREATE-DB-OPEN-1 (#408): verify-db-schema.py open modes, exercised
through the script's own functions — the write path (_add_missing_column)
must alter an existing db, and no mode may create a missing path."""

import importlib.util as _u
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.dialects import sqlite as _sa_sqlite

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "utils" / "verify-db-schema.py"


def _load():
    spec = _u.spec_from_file_location("verify_db_schema", _SCRIPT)
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _ColType:
    def compile(self, dialect=None):
        return "INTEGER"


class _Col:
    name = "b"
    nullable = True
    default = None
    type = _ColType()


def _scratch_db(tmp_path) -> Path:
    db = tmp_path / "s.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    conn.close()
    return db


def _dialect():
    d = _sa_sqlite.dialect()
    return d, d.identifier_preparer.quote


def test_add_missing_column_alters_existing_db(tmp_path):
    """_add_missing_column(mode=rw) performs the ALTER on an existing db.
    Pin: mode=ro here refuses the write, so this test fails on it."""
    v = _load()
    db = _scratch_db(tmp_path)
    dialect, quote = _dialect()
    out = v._add_missing_column(db, "t", _Col(), dialect, quote)
    assert out is None  # None = repair applied, not a refusal message
    cols = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(t)")]
    assert "b" in cols


def test_add_missing_column_refuses_missing_path(tmp_path):
    """mode=rw must refuse a missing db — and must not create the file.
    Pin: mode=rwc would create it, so this test fails on rwc."""
    v = _load()
    ghost = tmp_path / "ghost.db"
    dialect, quote = _dialect()
    with pytest.raises(sqlite3.OperationalError):
        v._add_missing_column(ghost, "t", _Col(), dialect, quote)
    assert not ghost.exists()


def test_reader_helpers_refuse_missing_path(tmp_path):
    """_actual_tables/_actual_columns open mode=ro — refuse missing."""
    v = _load()
    ghost = tmp_path / "g2.db"
    with pytest.raises(sqlite3.OperationalError):
        v._actual_tables(ghost)
    assert not ghost.exists()


def test_actual_columns_refuses_missing_path(tmp_path):
    """_actual_columns (mode=ro at :94) must also refuse + not create —
    the open site the earlier file missed."""
    v = _load()
    ghost = tmp_path / "g3.db"
    with pytest.raises(sqlite3.OperationalError):
        v._actual_columns(ghost, "t")
    assert not ghost.exists()
