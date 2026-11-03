"""Tests for SNAPSHOT-SIGN-UNCHECKED-ROOT-1: the signer must refuse a manifest
whose state root was skipped or does not match (unless --allow-unchecked-root),
the in-place write must be atomic, and the generator must read the db inside
one read transaction so the manifest is a single consistent snapshot.

Fixtures only: throwaway keys, scratch chain.db files — never real /var or
/etc paths.
"""

import importlib.util
import json
import os
import sqlite3
import sys
import types
from pathlib import Path

import pytest

eth_account = pytest.importorskip("eth_account")
from eth_account import Account  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGN = REPO_ROOT / "scripts" / "ops" / "sign-snapshot-manifest.py"
GEN = REPO_ROOT / "scripts" / "ops" / "snapshot-manifest.py"
CHAIN = "ait-test"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def signer():
    return _load(SIGN, "sign_snapshot_manifest")


@pytest.fixture(scope="module")
def gen():
    return _load(GEN, "snapshot_manifest")


@pytest.fixture()
def key(tmp_path):
    acct = Account.create()
    p = tmp_path / "k.hex"
    h = acct.key.hex()
    p.write_text((h[2:] if h.startswith("0x") else h) + "\n")
    p.chmod(0o600)
    return p


def _mk_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, state_root TEXT);
        CREATE TABLE bond (chain_id TEXT, address TEXT, amount INTEGER, created_at TEXT);
        CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER);
        CREATE TABLE escrow (job_id TEXT, amount INTEGER);
        """
    )
    conn.execute("INSERT INTO block VALUES (?, ?, ?, ?)", (CHAIN, 7, "0xdead", "0xroot"))
    conn.execute("INSERT INTO bond VALUES (?, ?, ?, ?)", (CHAIN, "addr1", 100, "ts"))
    conn.commit()
    conn.close()
    return path


def _manifest_file(gen_tool, db: Path, path: Path, *, state_root=None) -> Path:
    conn = gen_tool.connect_ro(str(db))
    m = gen_tool.build_manifest(conn, str(db), CHAIN, with_state_root=False)
    conn.close()
    if state_root is not None:
        m["state_root"] = state_root
    path.write_text(json.dumps(m, indent=2, sort_keys=True))
    return path


def test_sign_skipped_root_refused(signer, gen, tmp_path, key, capsys):
    db = _mk_db(tmp_path / "m.db")
    mf = _manifest_file(gen, db, tmp_path / "m.json")  # state_root.skipped true
    capsys.readouterr()
    try:
        rc = signer.main([str(mf), "--key-file", str(key)])
    except SystemExit:
        rc = 2
    err = capsys.readouterr().err
    assert rc == 2 and "state_root" in err
    assert "signature" not in json.loads(mf.read_text()) or not json.loads(mf.read_text()).get("signature")


def test_sign_mismatched_root_refused(signer, gen, tmp_path, key, capsys):
    db = _mk_db(tmp_path / "m.db")
    mf = _manifest_file(
        gen,
        db,
        tmp_path / "m.json",
        state_root={"recorded": "0xroot", "recomputed": "0xother", "match": False, "skipped": False},
    )
    capsys.readouterr()
    try:
        rc = signer.main([str(mf), "--key-file", str(key)])
    except SystemExit:
        rc = 2
    assert rc == 2 and "state_root" in capsys.readouterr().err


def test_sign_unchecked_root_override_flag(signer, gen, tmp_path, key):
    db = _mk_db(tmp_path / "m.db")
    mf = _manifest_file(gen, db, tmp_path / "m.json")
    assert signer.main([str(mf), "--key-file", str(key), "--allow-unchecked-root"]) == 0
    assert json.loads(mf.read_text())["signature"].startswith("0x")


def test_kill_mid_write_leaves_old_manifest(signer, gen, tmp_path, key, monkeypatch):
    """A crash during the write must not destroy the unsigned original."""
    db = _mk_db(tmp_path / "m.db")
    mf = _manifest_file(gen, db, tmp_path / "m.json")
    before = mf.read_bytes()

    def boom(_fd):
        raise OSError("ENOSPC")

    monkeypatch.setattr(signer.os, "fsync", boom)
    try:
        rc = signer.main([str(mf), "--key-file", str(key), "--allow-unchecked-root"])
    except SystemExit:
        rc = 2
    assert rc == 2
    assert mf.read_bytes() == before  # torn/truncated write must be impossible


def test_generator_reads_one_snapshot(gen, tmp_path, monkeypatch):
    """A commit landing mid-build must not leak into row_counts/digests.

    WAL mode lets the writer commit while the reader holds its snapshot:
    with one read transaction the manifest is a single consistent snapshot;
    without it, the second half of the read sees the newer commit.
    """
    db = tmp_path / "live.db"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, state_root TEXT);
        CREATE TABLE bond (chain_id TEXT, address TEXT, amount INTEGER, created_at TEXT);
        CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER);
        CREATE TABLE escrow (job_id TEXT, amount INTEGER);
        """
    )
    writer.execute("INSERT INTO block VALUES (?, ?, ?, ?)", (CHAIN, 7, "0xdead", "0xroot"))
    writer.execute("INSERT INTO bond VALUES (?, ?, ?, ?)", (CHAIN, "addr1", 100, "ts"))
    writer.commit()
    try:
        real_probe = gen._load_side_root_probe()
        committed = {"done": False}

        def td(conn, table, *, canonical=False):
            if not committed["done"]:
                committed["done"] = True
                writer.execute("INSERT INTO bond VALUES ('x', 'y', 5, 't')")
                writer.commit()
            return real_probe.table_digest(conn, table, canonical=canonical)

        wrapper = types.SimpleNamespace(
            CANDIDATE_TABLES=real_probe.CANDIDATE_TABLES,
            CONTROL_TABLES=real_probe.CONTROL_TABLES,
            table_digest=td,
        )
        monkeypatch.setattr(gen, "_load_side_root_probe", lambda: wrapper)

        conn = gen.connect_ro(str(db))
        m = gen.build_manifest(conn, str(db), CHAIN, with_state_root=False)
        conn.close()
        # Snapshot taken before the mid-read commit: bond still has 1 row.
        assert m["row_counts"]["bond"] == 1
        assert m["table_digests"]["candidates"]["bond"]["rows"] == 1
    finally:
        writer.close()


def test_manifest_mode_preserved(signer, gen, tmp_path, key):
    db = _mk_db(tmp_path / "m.db")
    mf = _manifest_file(gen, db, tmp_path / "m.json")
    mf.chmod(0o640)
    assert signer.main([str(mf), "--key-file", str(key), "--allow-unchecked-root"]) == 0
    assert os.stat(mf).st_mode & 0o777 == 0o640
    assert json.loads(mf.read_text())["signature"].startswith("0x")
