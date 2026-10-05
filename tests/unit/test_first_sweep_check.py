"""Fixture tests for scripts/ops/first-sweep-check.py.

Builds a minimal chain.db (the real ``transaction``/``account``/
``chain_parameter``/``chain_parameter_history`` schema, minus unused
columns), seeds a full lock → release → sweep lifecycle, and drives the
checker's ``main()`` end-to-end. Stdlib only — mirrors the checker.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "first-sweep-check.py"
spec = importlib.util.spec_from_file_location("first_sweep_check", SCRIPT)
fsc = importlib.util.module_from_spec(spec)
sys.modules["first_sweep_check"] = fsc
spec.loader.exec_module(fsc)

CHAIN = "testchain"
AUTHORITY = "0x03DF9Ed3788E5BA3991e6788036f9D171f027716"
FEE_RECIP = "0x716a56468DD4A11A91116920F9E8892BbDD7b1B8"
CLIENT = "0x11c3b1C69E05c04Ab8c8aCF12ddE32E4B9F51111"
PROVIDER = "0x4A5b21C74A63dF57d830DEdb7b7AcfCf8Aba1111"
JOB = "first-sweep-fixture"
CUSTODY = fsc.escrow_address(JOB)  # 0x156742a97E886803B98c9ba654e2d76b70F56a81


def _mk_db(path: Path, *, mutate=None) -> Path:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE "transaction" (
            chain_id TEXT, tx_hash TEXT PRIMARY KEY, block_height INTEGER,
            sender TEXT, recipient TEXT, payload TEXT, nonce INTEGER,
            value INTEGER, fee INTEGER, type TEXT, status TEXT
        );
        CREATE TABLE account (
            chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER,
            PRIMARY KEY (chain_id, address)
        );
        CREATE TABLE chain_parameter (
            chain_id TEXT, parameter TEXT, value TEXT, applied_height INTEGER,
            PRIMARY KEY (chain_id, parameter)
        );
        CREATE TABLE chain_parameter_history (
            chain_id TEXT, parameter TEXT, value TEXT, applied_height INTEGER
        );
        """
    )
    db.execute("INSERT INTO chain_parameter VALUES (?,?,?,?)", (CHAIN, "escrow_settlement_authority", AUTHORITY, 1))
    db.execute("INSERT INTO chain_parameter VALUES (?,?,?,?)", (CHAIN, "escrow_fee_recipient", FEE_RECIP, 1))
    txs = [
        # h5: funder tops up the authority so its balance stays ledger-explainable
        ("h5-fund", 5, "funder", AUTHORITY, None, 0, 10000, 0, "TRANSFER"),
        # h10: client locks 1000 — apply overrides recipient to custody (row keeps submitter's recipient)
        ("h10-lock", 10, CLIENT, AUTHORITY, {"job_id": JOB}, 0, 1000, 0, "ESCROW_LOCK"),
        # h20: release 900 to provider (authority pays only fee=36; custody pays 900)
        ("h20-rel", 20, AUTHORITY, PROVIDER, {"job_id": JOB}, 1, 900, 36, "ESCROW_RELEASE"),
        # h21: sweep the 100 residue to the fee recipient
        ("h21-sweep", 21, AUTHORITY, FEE_RECIP, {"job_id": JOB}, 2, 100, 36, "ESCROW_FEE_SWEEP"),
    ]
    for h, height, sender, recip, payload, nonce, value, fee, ttype in txs:
        db.execute(
            'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (CHAIN, h, height, sender, recip, json.dumps(payload) if payload else None, nonce, value, fee, ttype, "sealed"),
        )
    # Balances: custody 1000-900-100=0; recip +100; authority 10000-36-36=9928
    for addr, bal, nonce in [
        (CUSTODY, 0, 0),
        (FEE_RECIP, 100, 0),
        (AUTHORITY, 9928, 2),
        (PROVIDER, 900, 0),
        (CLIENT, 0, 1),
    ]:
        db.execute("INSERT INTO account VALUES (?,?,?,?)", (CHAIN, addr, bal, nonce))
    if mutate:
        mutate(db)
    db.commit()
    db.close()
    return path


def _run(capsys, *argv):
    rc = fsc.main(list(argv))
    out = capsys.readouterr().out
    return rc, out


def test_keccak_known_answers():
    # Real implementations: _escrow_address("sweep-job-1") et al. computed on a live node.
    assert fsc.keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert fsc.escrow_address("sweep-job-1") == "0xf57D3980C47977ef29E69c80370c966A122977d8"
    assert fsc.escrow_address("canary-escrow-27260") == "0x748C863cF060bc9656cb79ECa61Fe0f6E5266f7a"
    assert CUSTODY == "0x156742a97E886803B98c9ba654e2d76b70F56a81"


def test_happy_path_all_pass(tmp_path, capsys):
    db = _mk_db(tmp_path / "hub.db")
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert rc == 0
    for name in (
        "sweep.sealed",
        "sweep.signer",
        "sweep.recipient",
        "sweep.value",
        "custody.zero",
        "recipient.delta",
        "authority.delta",
        "authority.nonce",
    ):
        assert f"PASS {name}" in out, out
    assert "FAIL" not in out


def test_latest_selects_the_sweep(tmp_path, capsys):
    db = _mk_db(tmp_path / "hub.db")
    rc, out = _run(capsys, "--chain-id", CHAIN, "--latest", str(db))
    assert rc == 0
    assert "h21-sweep" in out
    assert "FAIL" not in out


def test_duplicate_sweep_rows_are_reported_not_trusted(tmp_path, capsys):
    """A second sealed sweep row (dup submit or failed-apply record) must be
    surfaced — the checker verifies the earliest and flags the rest."""

    def mut(d):
        d.execute(
            'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (
                CHAIN,
                "h22-sweep-dupe",
                22,
                AUTHORITY,
                FEE_RECIP,
                json.dumps({"job_id": JOB}),
                3,
                0,
                36,
                "ESCROW_FEE_SWEEP",
                "sealed",
            ),
        )
        d.execute("UPDATE account SET nonce=3 WHERE address=?", (AUTHORITY,))

    db = _mk_db(tmp_path / "hub.db", mutate=mut)
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert "SKIP sweep.duplicates" in out and "1 further sealed sweep" in out


def test_missing_sweep_fails(tmp_path, capsys):
    db = _mk_db(tmp_path / "hub.db", mutate=lambda d: d.execute("DELETE FROM \"transaction\" WHERE type='ESCROW_FEE_SWEEP'"))
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert rc == 1
    assert "FAIL sweep.sealed" in out


def test_wrong_signer_fails(tmp_path, capsys):
    def mut(d):
        d.execute("UPDATE \"transaction\" SET sender=? WHERE type='ESCROW_FEE_SWEEP'", (CLIENT,))

    db = _mk_db(tmp_path / "hub.db", mutate=mut)
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert rc == 1
    assert "FAIL sweep.signer" in out
    assert "NOT the authority" in out


def test_wrong_recipient_fails(tmp_path, capsys):
    def mut(d):
        d.execute("UPDATE \"transaction\" SET recipient=? WHERE type='ESCROW_FEE_SWEEP'", (CLIENT,))

    db = _mk_db(tmp_path / "hub.db", mutate=mut)
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert rc == 1
    assert "FAIL sweep.recipient" in out


def test_value_mismatch_fails(tmp_path, capsys):
    def mut(d):
        d.execute("UPDATE \"transaction\" SET value=90 WHERE type='ESCROW_FEE_SWEEP'")

    db = _mk_db(tmp_path / "hub.db", mutate=mut)
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert rc == 1
    assert "FAIL sweep.value" in out


def test_nonzero_custody_fails(tmp_path, capsys):
    def mut(d):
        d.execute("UPDATE account SET balance=7 WHERE address=?", (CUSTODY,))

    db = _mk_db(tmp_path / "hub.db", mutate=mut)
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert rc == 1
    assert "FAIL custody.zero" in out
    assert "detector reads 7" in out


def test_cross_host_disagreement_fails(tmp_path, capsys):
    good = _mk_db(tmp_path / "hub.db")

    def mut(d):
        d.execute("UPDATE \"transaction\" SET tx_hash='evil-hash' WHERE type='ESCROW_FEE_SWEEP'")

    bad = _mk_db(tmp_path / "node2.db", mutate=mut)
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(good), str(bad))
    assert rc == 1
    assert "FAIL cross-host" in out


def test_cross_host_agreement_passes(tmp_path, capsys):
    a = _mk_db(tmp_path / "hub.db")
    b = _mk_db(tmp_path / "node2.db")
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(a), str(b))
    assert rc == 0
    assert "PASS cross-host" in out


def test_param_history_uses_sweep_height(tmp_path, capsys):
    """An authority rotation AFTER the sweep must not rewrite the check —
    the signer is compared to the authority in force at the sweep height."""

    def mut(d):
        new_auth = "0x02B8F2C61DB19B04ab68cfb43d0605E63dE74c5B"
        d.execute(
            "UPDATE chain_parameter SET value=?, applied_height=30 WHERE parameter='escrow_settlement_authority'",
            (new_auth,),
        )
        d.execute(
            "INSERT INTO chain_parameter_history VALUES (?,?,?,?)",
            (CHAIN, "escrow_settlement_authority", AUTHORITY, 1),
        )

    db = _mk_db(tmp_path / "hub.db", mutate=mut)
    rc, out = _run(capsys, "--chain-id", CHAIN, "--job-id", JOB, str(db))
    assert rc == 0
    assert "PASS sweep.signer" in out


def test_readonly_open(tmp_path):
    db = _mk_db(tmp_path / "hub.db")
    conn = fsc._open_ro(str(db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute('INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)', tuple("x" * 11))
    conn.close()
