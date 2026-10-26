"""BACKUP-VERIFY-1: backup-verify.py restores a generation in scratch."""

import gzip
import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("backup_verify", Path(__file__).parents[1] / "scripts/ops/backup-verify.py")
bv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bv)


def _mk_chain_dump(dest: Path, table: str = "blocks") -> None:
    db = dest.parent / "_tmp.db"
    conn = sqlite3.connect(db)
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
    conn.execute(f"INSERT INTO {table} VALUES (1), (2), (3)")
    conn.commit()
    conn.close()
    out = subprocess.run(["sqlite3", str(db), ".dump"], capture_output=True)
    dest.write_bytes(gzip.compress(out.stdout))
    db.unlink()


def _mk_svc(dest: Path) -> None:
    src = dest.parent / "_svc.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    dest.write_bytes(gzip.compress(src.read_bytes()))
    src.unlink()


def _mk_pg(dest: Path) -> None:
    sql = (
        b"-- PostgreSQL database dump\nSET standard_conforming_strings = on;\n"
        b"CREATE TABLE x (id integer) OWNER TO aitbc_marketplace;\n"
        b"-- PostgreSQL database dump complete\n"
    )
    dest.write_bytes(gzip.compress(sql))


@pytest.fixture
def good_set(tmp_path):
    gen = tmp_path / "20260101_010000"
    gen.mkdir()
    _mk_chain_dump(gen / "chain_ait-hub_chain.db.gz")
    _mk_svc(gen / "svc_hermes_state.db.gz")
    _mk_pg(gen / "postgres_aitbc_marketplace.sql.gz")
    return gen


def test_good_set_passes(good_set, tmp_path):
    errs, rep = bv.verify_set(good_set, tmp_path / "sc", None)
    assert errs == []
    assert rep["chain"][0]["ok"] and rep["svc"][0]["ok"]
    assert rep["pg"]["postgres_aitbc_marketplace.sql.gz"]["roles"] == ["aitbc_marketplace"]


def test_corrupt_chain_dump_fails(good_set, tmp_path):
    (good_set / "chain_bad_chain.db.gz").write_bytes(gzip.compress(b"not sql at all {"))
    errs, _ = bv.verify_set(good_set, tmp_path / "sc", None)
    assert any("chain_bad" in e or "integrity" in e for e in errs)


def test_pg_dump_missing_header(good_set, tmp_path):
    (good_set / "postgres_fake.sql.gz").write_bytes(gzip.compress(b"hello"))
    errs, rep = bv.verify_set(good_set, tmp_path / "sc", None)
    assert any("postgres_fake" in e for e in errs)


def test_baseline_row_count(good_set, tmp_path):
    baseline = {"chain_ait-hub_chain.db.gz": {"blocks": 3}}
    errs, rep = bv.verify_set(good_set, tmp_path / "sc", baseline)
    assert errs == []
    assert rep["chain"][0]["rows"]["blocks"] == 3
    baseline = {"chain_ait-hub_chain.db.gz": {"blocks": 10}}
    errs, _ = bv.verify_set(good_set, tmp_path / "sc2", baseline)
    assert any("below baseline" in e for e in errs)


def test_main_exit_codes(good_set, tmp_path, capsys):
    sys.argv = ["backup-verify.py", "--set", str(good_set), "--scratch", str(tmp_path / "sc2")]
    assert bv.main() == 0
    sys.argv = ["backup-verify.py", "--base", str(tmp_path / "nonexistent")]
    assert bv.main() == 2
