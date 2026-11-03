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
    import datetime

    gen = tmp_path / datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
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


def test_aborted_chain_dump_fails(good_set, tmp_path):
    """#910: a dump ending in 'ROLLBACK; -- due to errors' must not be CLEAN."""
    aborted = (
        b"BEGIN TRANSACTION;\nCREATE TABLE blocks (id INTEGER PRIMARY KEY);\n"
        b"INSERT INTO blocks VALUES (1);\nROLLBACK; -- due to errors\n"
    )
    (good_set / "chain_broken_chain.db.gz").write_bytes(gzip.compress(aborted))
    errs, rep = bv.verify_set(good_set, tmp_path / "sc", None)
    assert any("chain_broken" in e for e in errs)


def test_commitless_chain_dump_fails(good_set, tmp_path):
    """#910: a truncated dump without COMMIT is not a snapshot."""
    (good_set / "chain_trunc_chain.db.gz").write_bytes(
        gzip.compress(b"BEGIN TRANSACTION;\nCREATE TABLE blocks (id INTEGER);\n")
    )
    errs, _ = bv.verify_set(good_set, tmp_path / "sc", None)
    assert any("chain_trunc" in e for e in errs)


def test_stale_newest_set_fails(good_set, tmp_path):
    """#911: an old-named set must not read CLEAN."""
    stale = tmp_path / "20200102_000000"
    stale.mkdir()
    (stale / "chain_x_chain.db.gz").write_bytes(
        gzip.compress(b"BEGIN TRANSACTION;\nCREATE TABLE blocks (id INTEGER);\nINSERT INTO blocks VALUES (1);\nCOMMIT;\n")
    )
    errs, rep = bv.verify_set(stale, tmp_path / "sc", None)
    assert any("old" in e for e in errs)


def test_empty_newest_set_fails(tmp_path):
    """#911: a newest dir with zero artifacts is an error, not CLEAN."""
    empty = tmp_path / "20200102_000000"
    empty.mkdir()
    errs, rep = bv.verify_set(empty, tmp_path / "sc", None)
    assert any("no chain" in e for e in errs)


def test_user_scratch_dir_survives(tmp_path, good_set):
    """#912: an existing --scratch dir and its files survive a run."""
    sc = tmp_path / "operator-dir"
    sc.mkdir()
    keep = sc / "keep.txt"
    keep.write_text("do not delete")
    errs, _ = bv.verify_set(good_set, tmp_path / "sc2", None)
    # now drive the main() scratch path — call the same code path via subprocess
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts/ops/backup-verify.py"),
            "--set",
            str(good_set),
            "--scratch",
            str(sc),
        ],
        capture_output=True,
        text=True,
    )
    assert keep.exists(), "the run deleted the operator's scratch dir"


def test_no_maintenance_script_pulls_into_live_checkout():
    """#903: scripts must not `git pull` a live checkout or install a missing
    requirements.txt (weekly_maintenance.sh is retired)."""
    import re

    bad = []
    # deployment/update scripts pull on purpose — the card is about
    # maintenance/ops scripts silently mutating the live checkout.
    globs = [
        p
        for p in Path(__file__).parents[1].glob("scripts/**/*.sh")
        if "/deployment/" not in str(p) and "workflow-agent/" not in str(p)
    ]
    for sh in globs:
        for line in sh.read_text(errors="replace").splitlines():
            ls = line.strip()
            if ls.startswith(("#", "echo", "printf")) or '"' in ls.split("git")[0]:
                continue
            if re.search(r"git\s+pull", ls) and "/opt/aitbc" in ls:
                bad.append(f"{sh}: {ls[:60]}")
            if "pip install -r requirements.txt" in ls:
                bad.append(f"{sh}: installs missing requirements.txt")
    assert bad == []
