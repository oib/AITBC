"""Tests for scripts/ops/sign-snapshot-manifest.py + verify-snapshot-manifest.py.

Fixtures only: throwaway keys generated inside the test (tmp_path files,
never a real key), tiny fixture chain.db + manifest built via the real
generator — same style as test_snapshot_manifest.py.
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


def _keyfile(tmp_path: Path, mode: int = 0o600, name: str = "k.hex") -> Path:
    acct = Account.create()
    p = tmp_path / name
    h = acct.key.hex()
    p.write_text((h[2:] if h.startswith("0x") else h) + "\n")
    p.chmod(mode)
    return p


def _manifest_file(gen_tool, tmp_path: Path, name: str = "m.json") -> Path:
    db = tmp_path / (Path(name).stem + ".db")
    conn = sqlite3.connect(db)
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
    conn = gen_tool.connect_ro(str(db))
    m = gen_tool.build_manifest(conn, str(db), CHAIN, with_state_root=False)
    conn.close()
    p = tmp_path / name
    p.write_text(json.dumps(m, indent=2, sort_keys=True))
    return p


def test_sign_then_verify_ok(signer, verifier, gen, tmp_path, capsys):
    key = _keyfile(tmp_path)
    mf = _manifest_file(gen, tmp_path)
    assert signer.main([str(mf), "--key-file", str(key)]) == 0
    signed = json.loads(mf.read_text())
    assert signed["signature"].startswith("0x") and len(signed["signature"]) == 132
    rc = verifier.main([str(mf), "--trusted-address", Account.from_key("0x" + key.read_text().strip()).address])
    out = capsys.readouterr().out
    assert rc == 0 and "signature-check OK" in out and out.strip().endswith("OK")


def test_wrong_trusted_address_fails(signer, verifier, gen, tmp_path, capsys):
    key = _keyfile(tmp_path)
    mf = _manifest_file(gen, tmp_path)
    signer.main([str(mf), "--key-file", str(key)])
    capsys.readouterr()
    rc = verifier.main([str(mf), "--trusted-address", Account.create().address])
    out = capsys.readouterr().out
    assert rc == 1 and "signature-check FAIL" in out and out.strip().endswith("FAIL")


def test_tampered_content_fails(signer, verifier, gen, tmp_path, capsys):
    key = _keyfile(tmp_path)
    mf = _manifest_file(gen, tmp_path)
    signer.main([str(mf), "--key-file", str(key)])
    m = json.loads(mf.read_text())
    m["head"]["height"] = 8  # tamper after signing
    mf.write_text(json.dumps(m, indent=2, sort_keys=True))
    rc = verifier.main([str(mf), "--trusted-address", Account.from_key("0x" + key.read_text().strip()).address])
    out = capsys.readouterr().out
    assert rc == 1 and "FAIL" in out


def test_missing_signature_fails(verifier, gen, tmp_path, capsys):
    mf = _manifest_file(gen, tmp_path)  # unsigned, signature == ""
    rc = verifier.main([str(mf)])
    out = capsys.readouterr().out
    assert rc == 1 and "no signature" in out


def test_signature_copied_from_other_manifest_fails(signer, verifier, gen, tmp_path, capsys):
    key = _keyfile(tmp_path)
    mf1, mf2 = _manifest_file(gen, tmp_path, "a.json"), _manifest_file(gen, tmp_path, "b.json")
    signer.main([str(mf1), "--key-file", str(key)])
    sig = json.loads(mf1.read_text())["signature"]
    m2 = json.loads(mf2.read_text())
    m2["head"]["height"] = 9  # different content, then graft the signature
    m2["signature"] = sig
    mf2.write_text(json.dumps(m2, indent=2, sort_keys=True))
    rc = verifier.main([str(mf2), "--trusted-address", Account.from_key("0x" + key.read_text().strip()).address])
    out = capsys.readouterr().out
    assert rc == 1 and "signature-check FAIL" in out


def test_key_file_mode_644_refused(signer, gen, tmp_path, capsys):
    key = _keyfile(tmp_path, mode=0o644)
    mf = _manifest_file(gen, tmp_path)
    rc = signer.main([str(mf), "--key-file", str(key)])
    out = capsys.readouterr()
    assert rc == 2 and "mode 600" in out.err


def test_already_signed_refused(signer, gen, tmp_path, capsys):
    key = _keyfile(tmp_path)
    mf = _manifest_file(gen, tmp_path)
    assert signer.main([str(mf), "--key-file", str(key)]) == 0
    rc = signer.main([str(mf), "--key-file", str(key)])
    assert rc == 2 and "already carries a signature" in capsys.readouterr().err


def test_db_content_check_match(signer, verifier, gen, tmp_path, capsys):
    key = _keyfile(tmp_path)
    mf = _manifest_file(gen, tmp_path)  # manifest built from tmp_path/m.db
    signer.main([str(mf), "--key-file", str(key)])
    capsys.readouterr()
    rc = verifier.main(
        [
            str(mf),
            "--trusted-address",
            Account.from_key("0x" + key.read_text().strip()).address,
            "--db",
            str(tmp_path / "m.db"),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0 and "content-check OK" in out


def test_db_content_check_mismatch(signer, verifier, gen, tmp_path, capsys):
    key = _keyfile(tmp_path)
    mf = _manifest_file(gen, tmp_path)
    signer.main([str(mf), "--key-file", str(key)])
    capsys.readouterr()
    # mutate the db the manifest attests
    conn = sqlite3.connect(tmp_path / "m.db")
    conn.execute("UPDATE bond SET amount=999 WHERE chain_id=?", (CHAIN,))
    conn.commit()
    conn.close()
    rc = verifier.main(
        [
            str(mf),
            "--trusted-address",
            Account.from_key("0x" + key.read_text().strip()).address,
            "--db",
            str(tmp_path / "m.db"),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1 and "content-check FAIL" in out
