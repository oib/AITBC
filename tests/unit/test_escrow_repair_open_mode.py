"""NO-CREATE-DB-OPEN-1 (#408): escrow-repair's apply open is mode=rw —
write-capable on an existing file, refusing to create a missing one.
(Own file so cbee1be9c applies without the step-1 test file.)"""

import sqlite3
import pytest


def test_mode_rw_writes_existing_db(tmp_path):
    db = tmp_path / "repair.db"
    db.touch()  # an existing (even empty) file opens rw as an empty db
    conn = sqlite3.connect(f"file:{db}?mode=rw", uri=True)
    conn.execute("create table t (x int)")
    conn.commit()
    conn.execute("insert into t values (1)")
    conn.commit()
    conn.close()
    assert db.exists()


def test_mode_rw_refuses_missing_db(tmp_path):
    db = tmp_path / "ghost.db"
    with pytest.raises(sqlite3.OperationalError):
        sqlite3.connect(f"file:{db}?mode=rw", uri=True)
    assert not db.exists()


def test_script_apply_on_missing_path_creates_nothing(tmp_path):
    """_cmd_apply against a missing db must refuse AND leave no file.
    Pin: mode=rwc at escrow-repair.py:274 would create it -> this fails."""
    import argparse
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "escrow-repair.py"
    spec = importlib.util.spec_from_file_location("escrow_repair", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ghost = tmp_path / "ghost.db"
    args = argparse.Namespace(db=str(ghost), write=True, allow_live_path=False, json=False)
    with pytest.raises(sqlite3.OperationalError):
        mod._cmd_apply(args)
    assert not ghost.exists()
