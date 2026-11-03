"""Content-check tests for verify-snapshot-manifest.py --db (SNAPSHOT-VERIFY-CONTENT-GAPS-1).

The verifier must FAIL (exit 1, a ``content-check FAIL`` line) on: a chain the
db does not hold, a head mismatch, a row_counts mismatch, a skipped or
unrecomputable state root, a recorded root that differs from the db head's,
and candidate/control tables missing from the manifest.

All manifests are honestly signed with a throwaway key and verified with
``--trusted-address`` so the content check — never the signature — is what
decides. Fixtures are tiny chain.db files; scratch dirs only.
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

eth_account = pytest.importorskip("eth_account")
from eth_account import Account  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGN = REPO_ROOT / "scripts" / "ops" / "sign-snapshot-manifest.py"
VERIFY = REPO_ROOT / "scripts/ops" / "verify-snapshot-manifest.py"
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
def verifier():
    return _load(VERIFY, "verify_snapshot_manifest")


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
    return p, acct.address


def _mk_db(path: Path, *, chain=CHAIN, height=7, head_hash="0xdead", state_root="0xroot", bond_amount=100):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, state_root TEXT);
        CREATE TABLE bond (chain_id TEXT, address TEXT, amount INTEGER, created_at TEXT);
        CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER);
        CREATE TABLE escrow (job_id TEXT, amount INTEGER);
        """
    )
    conn.execute("INSERT INTO block VALUES (?, ?, ?, ?)", (chain, height, head_hash, state_root))
    conn.execute("INSERT INTO bond VALUES (?, ?, ?, ?)", (chain, "addr1", bond_amount, "ts"))
    conn.commit()
    conn.close()
    return path


def _manifest(gen_tool, db, chain=CHAIN):
    conn = gen_tool.connect_ro(str(db))
    m = gen_tool.build_manifest(conn, str(db), chain, with_state_root=False)
    conn.close()
    return m


def _sign(signer, manifest: dict, path: Path, key_file: Path) -> Path:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    try:
        rc = signer.main([str(path), "--key-file", str(key_file), "--allow-unchecked-root"])
    except SystemExit:
        rc = 2  # pre-#858 signer lacks the flag
    if rc != 0:
        assert signer.main([str(path), "--key-file", str(key_file)]) == 0
    return path


def _verify(verifier, mf, address, db, *extra):
    return verifier.main([str(mf), "--trusted-address", address, "--db", str(db), *extra])


def test_chain_absent_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    m["chain_id"] = "other"  # chain the db does not hold
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db)
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out and out.strip().endswith("FAIL")


def test_head_mismatch_no_row_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    m["head"] = {"height": 77, "hash": "0xzz"}  # db head is (7, 0xdead)
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db)
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_row_counts_mismatch_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    m["row_counts"]["block"] = 999  # db has 1
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db)
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_row_counts_missing_table_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    del m["row_counts"]["escrow"]  # db table the manifest omits
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db)
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_skipped_state_root_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)  # with_state_root=False → skipped: true
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db)
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_skipped_state_root_waived_by_flag(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db, "--skip-state-root")
    out = capsys.readouterr().out
    assert rc == 0 and "content-check OK" in out


def test_unrecomputable_state_root_fails(signer, verifier, gen, tmp_path, key, capsys, monkeypatch):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    m["state_root"] = {"recorded": "0xroot", "recomputed": "0xroot", "match": True, "skipped": False}
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    monkeypatch.setattr(verifier, "_recompute_state_root", lambda *a: None)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db)
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_match_false_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    m["state_root"] = {"recorded": "0xroot", "recomputed": "0xother", "match": False, "skipped": False}
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db)
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_recorded_root_differs_from_head_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    m["state_root"]["recorded"] = "0xnotroot"  # db head block carries 0xroot
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db, "--skip-state-root")
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_missing_candidate_table_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    del m["table_digests"]["candidates"]["bond"]  # verifier's probe requires it
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db, "--skip-state-root")
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_missing_control_table_fails(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    del m["table_digests"]["controls"]["escrow"]
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db, "--skip-state-root")
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out


def test_clean_manifest_passes(signer, verifier, gen, tmp_path, key, capsys):
    key_file, addr = key
    db = _mk_db(tmp_path / "m.db")
    m = _manifest(gen, db)
    mf = _sign(signer, m, tmp_path / "m.json", key_file)
    capsys.readouterr()
    rc = _verify(verifier, mf, addr, db, "--skip-state-root")
    out = capsys.readouterr().out
    assert rc == 0 and out.strip().endswith("OK")
