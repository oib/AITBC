"""Fixture tests for scripts/ops/bridge_proof_dryrun.py (A36-3).

Builds a temp chain.db (real file — the script opens it via SQLite
mode=ro URI) with a block whose proposer signature and metadata
attestations are signed by fixture eth keys over the canonical header
message, plus bridge_validators rows. Asserts the candidate-set counts
and the exit code. Fixture keys only — nothing real is signed or read.
"""

from __future__ import annotations

import importlib.util
import json
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from eth_keys import keys

from aitbc.bridge.types import BridgeBlockHeader
from aitbc.bridge.verification import build_verification_message
from aitbc.crypto.crypto import sign_transaction_data

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ops/bridge_proof_dryrun.py"
spec = importlib.util.spec_from_file_location("bridge_proof_dryrun", SCRIPT)
dryrun = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dryrun
spec.loader.exec_module(dryrun)


def _key() -> tuple[str, str]:
    pk = keys.PrivateKey(secrets.token_bytes(32))
    return pk.to_hex(), str(pk.public_key.to_checksum_address())


CHAIN = "fixture-chain"
A, B_, C, D = (_key() for _ in range(4))  # the four attesters
X, Y = _key(), _key()  # registered but never attest


@pytest.fixture()
def chain_db(tmp_path: Path) -> Path:
    db = tmp_path / "chain.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE block (height INTEGER, chain_id TEXT, hash TEXT,"
        " parent_hash TEXT, proposer TEXT, state_root TEXT,"
        " bridge_state_root TEXT, signature TEXT, block_metadata TEXT)"
    )
    conn.execute(
        "CREATE TABLE bridge_validators (chain_id TEXT, address TEXT,"
        " public_key TEXT, epoch INTEGER, is_active INTEGER, registered_at TEXT)"
    )
    # Registered set: X and Y — neither attests (the production shape).
    for addr in (X[1], Y[1]):
        conn.execute(
            "INSERT INTO bridge_validators VALUES (?,?,?,?,?,?)",
            (CHAIN, addr, "0x04", 0, 1, "2026-09-16 20:14:00"),
        )
    header = BridgeBlockHeader(
        chain_id=CHAIN,
        height=100,
        hash="0xdeadbeef" * 8,
        parent_hash="0xfeedface" * 8,
        proposer=A[1],
        state_root="0x1234" * 16,
        bridge_state_root="0x5678" * 16,
    )
    message = build_verification_message(header)
    proposer_sig = sign_transaction_data(message, A[0])
    attestations = [{"validator": k[1], "signature": sign_transaction_data(message, k[0])} for k in (B_, C)]
    conn.execute(
        "INSERT INTO block VALUES (?,?,?,?,?,?,?,?,?)",
        (
            100,
            CHAIN,
            header.hash,
            header.parent_hash,
            header.proposer,
            header.state_root,
            header.bridge_state_root,
            proposer_sig,
            json.dumps({"attestations": attestations}),
        ),
    )
    conn.commit()
    conn.close()
    return db


def _run(chain_db: Path, *extra: str) -> int:
    argv = [
        "--db",
        str(chain_db),
        "--tail",
        "1",
        "--pair",
        f"{X[1]},{Y[1]}",
        "--consensus",
        f"{A[1]},{B_[1]},{C[1]},{D[1]}",
        *extra,
    ]
    return dryrun.main(argv)


def test_dryrun_counts_and_exit(chain_db: Path, capsys) -> None:
    rc = _run(chain_db)
    out = capsys.readouterr().out
    # Signers: proposer A + attesters B,C -> 3 of the 4 consensus members.
    assert rc == 0
    assert "attestations=2" in out
    assert "a_registered: 0/2FAIL" in out
    assert "b_planned_pair: 0/2FAIL" in out
    assert "c_attesters: 3/4OK" in out


def test_exit_1_when_c_cannot_meet(chain_db: Path, capsys) -> None:
    # Consensus override excludes every actual signer.
    rc = _run(chain_db, "--consensus", f"{X[1]},{Y[1]}")
    out = capsys.readouterr().out
    assert rc == 1
    assert "(c) met threshold on 0" in out


def test_no_signatures_in_output(chain_db: Path, capsys) -> None:
    _run(chain_db)
    out = capsys.readouterr().out
    assert "0x04" not in out.split("signers=")[0] or "signature" not in out
    # No 130-char hex blobs (signature material) anywhere in output.
    assert not any(len(tok) > 70 and tok.startswith("0x") for tok in out.split())


def test_read_only_uri(chain_db: Path) -> None:
    conn = dryrun.open_ro(str(chain_db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO block VALUES (1,'x','h','p','pr','s','b','','')")
    conn.close()
