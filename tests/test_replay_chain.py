"""REPLAY-HARNESS-1 — scripts/ops/replay-chain.py must genesis-replay bc-2.

Two defects blocked every genesis replay of a chain whose genesis.json lists
the bond accounts (bc-2's does):

1. ``_seed_genesis`` inserted every allocation verbatim. ``init_db`` creates
   the bond escrow/burn accounts *before* the seed runs, so a genesis file
   listing them collided on the ``(chain_id, address)`` primary key —
   ``sqlite3.IntegrityError`` before a single block imported.
2. ``_SnapshotSource.blocks_range`` serialized every block column except
   ``aux_state_root``. ``import_block`` verifies the committed side-table
   fingerprint at block version >= 14 against ``block_data["aux_state_root"]``
   and reads ``None`` when the key is absent — every v14 block rejected with
   "aux_state_root expected None, computed …".

The end-to-end test below builds a two-block snapshot whose block 1 carries a
signed, root-stamped transaction and an ``aux_state_root``, plus a genesis.json
that allocates the bond accounts, and runs the script as a subprocess — the
same invocation a full-history replay uses.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "replay-chain.py"

_spec = importlib.util.spec_from_file_location("replay_chain_ops", SCRIPT)
rc = importlib.util.module_from_spec(_spec)
sys.modules["replay_chain_ops"] = rc  # dataclass resolution needs sys.modules
_spec.loader.exec_module(rc)

import aitbc  # noqa: E402
import aitbc_chain  # noqa: E402
from aitbc.crypto.consensus_signing import sign_block_hash  # noqa: E402
from aitbc.crypto.crypto import derive_ethereum_address  # noqa: E402
from aitbc.utils import DEFAULT_TX_FEE_UNITS  # noqa: E402
from aitbc_chain.base_models import Account, Block, Transaction  # noqa: E402
from aitbc_chain.database import _bond_burn_address, _bond_escrow_address, ensure_bond_accounts  # noqa: E402
from aitbc_chain.metadata import chain_metadata  # noqa: E402
from aitbc_chain.rpc.utils import sign_transaction_data  # noqa: E402
from aitbc_chain.state import side_root_shadow  # noqa: E402
from aitbc_chain.state.state_root_utils import compute_state_root_full  # noqa: E402
from aitbc_chain.state.state_transition import StateTransition  # noqa: E402

CHAIN = "replay-harness-fixture"
VERSION = 14  # aux_state_root checks engage at v14+
T0 = datetime(2026, 1, 1, tzinfo=UTC)

KEY_ALICE = "0x" + "aa" * 32
KEY_PROPOSER = "0x" + "bb" * 32
ADDR_ALICE = derive_ethereum_address(KEY_ALICE)
ADDR_PROPOSER = derive_ethereum_address(KEY_PROPOSER)
ADDR_CAROL = derive_ethereum_address("0x" + "cc" * 32)  # created by the transfer
GENESIS_HASH = "0x" + "00" * 32
BLOCK1_HASH = "0x" + "11" * 32


def _allocations() -> list[dict]:
    return [
        # The collision case: genesis.json lists both bond accounts that
        # init_db's ensure_bond_accounts creates before seeding runs.
        {"address": _bond_escrow_address(), "balance": 0, "nonce": 0},
        {"address": _bond_burn_address(), "balance": 0, "nonce": 0},
        {"address": ADDR_ALICE, "balance": 1_000_000, "nonce": 0},
    ]


def _genesis_json(path: Path, allocations: list[dict] | None = None) -> Path:
    doc = {
        "genesis_hash": GENESIS_HASH,
        "block": {"hash": GENESIS_HASH, "allocations": []},
        "allocations": _allocations() if allocations is None else allocations,
        "parameters": {},
    }
    path.write_text(json.dumps(doc))
    return path


def _genesis_block() -> Block:
    return Block(
        chain_id=CHAIN,
        height=0,
        hash=GENESIS_HASH,
        parent_hash="0x00",
        proposer="genesis",
        timestamp=T0,
        tx_count=0,
        state_root="0x" + "00" * 32,
        bridge_state_root="0x" + "00" * 32,
        block_metadata=json.dumps({"state_transition_version": VERSION}),
        signature="",
    )


def _make_snapshot(path: Path, blocks: list[Block], txs: list[Transaction]) -> Path:
    engine = create_engine(f"sqlite:///{path}")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        for b in blocks:
            session.add(b)
        for t in txs:
            session.add(t)
        session.commit()
    engine.dispose()
    return path


def _signed_transfer() -> dict:
    tx = {
        "from": ADDR_ALICE,
        "to": ADDR_CAROL,
        "amount": 100,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "payload": {},
        "type": "TRANSFER",
        "chain_id": CHAIN,
        "tx_hash": "0x" + "42" * 32,
    }
    tx["signature"] = sign_transaction_data(tx, KEY_ALICE)
    return tx


def _expected_block1_roots(tmp_path: Path) -> tuple[str, str, str]:
    """Reproduce the replay target's seeded state, apply the tx the way the
    import path will, and read off the roots block 1 must stamp."""
    engine = create_engine(f"sqlite:///{tmp_path / 'expected.db'}")
    chain_metadata.create_all(engine)
    st = StateTransition()
    with Session(engine) as session:
        ensure_bond_accounts(session, CHAIN)
        seen = {a.address for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()}
        for alloc in _allocations():
            if alloc["address"] not in seen:
                session.add(
                    Account(
                        chain_id=CHAIN,
                        address=alloc["address"],
                        balance=int(alloc["balance"]),
                        nonce=int(alloc.get("nonce", 0)),
                    )
                )
        session.flush()
        tx = dict(_signed_transfer())
        tx["value"] = tx["amount"]
        ok, err = st.apply_transaction(session, CHAIN, tx, tx["tx_hash"], block_version=VERSION, block_height=1)
        assert ok, f"fixture tx must apply: {err}"
        session.flush()
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, VERSION)["fingerprint"]
    engine.dispose()
    # Empty bridge trie for a block with no BRIDGE_LOCKs.
    from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

    return str(root), str(aux), "0x" + MerklePatriciaTrie().get_root().hex()


def _block1(state_root: str, aux: str, bridge_root: str) -> Block:
    block = Block(
        chain_id=CHAIN,
        height=1,
        hash=BLOCK1_HASH,
        parent_hash=GENESIS_HASH,
        proposer=ADDR_PROPOSER,
        timestamp=T0 + timedelta(seconds=70),
        tx_count=1,
        state_root=state_root,
        bridge_state_root=bridge_root,
        aux_state_root=aux,
        block_metadata=json.dumps({"state_transition_version": VERSION}),
    )
    block.signature = sign_block_hash(block, KEY_PROPOSER)
    return block


def _tx_row(tx: dict) -> Transaction:
    return Transaction(
        chain_id=CHAIN,
        tx_hash=tx["tx_hash"],
        block_height=1,
        sender=tx["from"],
        recipient=tx["to"],
        payload=tx["payload"],
        envelope=dict(tx),
        type=tx["type"],
        value=tx["amount"],
        fee=tx["fee"],
        nonce=tx["nonce"],
        status="confirmed",
    )


def test_blocks_range_serves_aux_state_root(tmp_path):
    """The stub must forward aux_state_root — import_block verifies it at v14+."""
    aux = "ab" * 32
    b0 = _genesis_block()
    b1 = _block1("0x" + "22" * 32, aux, "0x" + "00" * 32)
    snap = _make_snapshot(tmp_path / "snap.db", [b0, b1], [])
    src = rc._SnapshotSource(str(snap), CHAIN)
    got = src.blocks_range(1, 1)["blocks"][0]
    assert got["aux_state_root"] == aux


def test_blocks_range_aux_column_absent_degrades_to_none(tmp_path):
    """Snapshots recorded before the aux_state_root column existed (the whole
    checkpoint-era test suite builds those) must still serve — the column is
    missing entirely, so serving None keeps old snapshots loadable instead of
    crashing the range fetch with IndexError."""
    path = tmp_path / "old-snap.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, parent_hash TEXT, "
        "proposer TEXT, timestamp TEXT, tx_count INTEGER, state_root TEXT, "
        "bridge_state_root TEXT, block_metadata TEXT, signature TEXT)"
    )
    db.execute(
        'CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, chain_id TEXT, block_height INTEGER, '
        "sender TEXT, recipient TEXT, payload TEXT, envelope TEXT, created_at TEXT)"
    )
    db.execute(
        "INSERT INTO block VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (CHAIN, 0, GENESIS_HASH, "0x00", "genesis", T0.isoformat(), 0, "0x" + "00" * 32, None, "{}", ""),
    )
    db.commit()
    db.close()
    src = rc._SnapshotSource(str(path), CHAIN)
    served = src.blocks_range(0, 0)["blocks"][0]
    assert "aux_state_root" in served
    assert served["aux_state_root"] is None


def test_seed_genesis_skips_init_db_bond_rows(tmp_path):
    """bc-2's genesis.json allocates the two bond accounts that init_db's
    ensure_bond_accounts already created — seeding must not collide."""
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    chain_metadata.create_all(engine)
    snap = _make_snapshot(tmp_path / "snap.db", [_genesis_block()], [])
    genesis = _genesis_json(tmp_path / "genesis.json")
    src = rc._SnapshotSource(str(snap), CHAIN)
    with Session(engine) as session:
        ensure_bond_accounts(session, CHAIN)
        before = len(session.exec(select(Account).where(Account.chain_id == CHAIN)).all())
        rc._seed_genesis(session, CHAIN, str(genesis), src)
        rows = session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
    got = {a.address for a in rows}
    want = {_bond_escrow_address(), _bond_burn_address(), ADDR_ALICE}
    assert got == want
    assert before == 2  # bonds seeded by init_db path
    assert len(rows) == 3  # no duplicates from the collision


def test_seed_genesis_warns_on_allocation_mismatch(tmp_path, capsys):
    """An init-seeded row whose balance disagrees with the allocation must
    surface as a warning, not silently win or silently lose."""
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    chain_metadata.create_all(engine)
    snap = _make_snapshot(tmp_path / "snap.db", [_genesis_block()], [])
    allocs = _allocations()
    allocs[0]["balance"] = 5  # bond escrow claims funds init_db never gave it
    genesis = _genesis_json(tmp_path / "genesis.json", allocs)
    src = rc._SnapshotSource(str(snap), CHAIN)
    with Session(engine) as session:
        ensure_bond_accounts(session, CHAIN)
        rc._seed_genesis(session, CHAIN, str(genesis), src)
        row = session.get(Account, (CHAIN, _bond_escrow_address()))
        assert row is not None and int(row.balance) == 0  # existing row kept
    assert _bond_escrow_address() in capsys.readouterr().err


def test_replay_two_block_chain_end_to_end(tmp_path):
    """Subprocess run of the real script: genesis.json with bond accounts +
    a v14 block carrying aux_state_root must replay to OK."""
    state_root, aux, bridge_root = _expected_block1_roots(tmp_path)
    tx = _signed_transfer()
    snap = _make_snapshot(
        tmp_path / "snapshot.db",
        [_genesis_block(), _block1(state_root, aux, bridge_root)],
        [_tx_row(tx)],
    )
    genesis = _genesis_json(tmp_path / "genesis.json")

    chain_src = Path(aitbc_chain.__file__).resolve().parents[1]
    aitbc_src = Path(aitbc.__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(chain_src), str(aitbc_src), env.get("PYTHONPATH", "")) if p)
    env["TMPDIR"] = str(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--snapshot",
            str(snap),
            "--genesis",
            str(genesis),
            "--chain-id",
            CHAIN,
            "--workdir",
            str(tmp_path / "target"),
            "--keep",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"replay failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "REPLAY OK: blocks 1..1 hash/state-root identical" in proc.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
