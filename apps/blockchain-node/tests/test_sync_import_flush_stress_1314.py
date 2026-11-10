"""#1314 R2 importer mirror — flush ordering under concurrent import + seal.

At ``block_version >= 24`` the importer flushes every sealed Transaction row
right after adding it (``sync_block_import`` ~L947) so later same-block
applies see it, mirroring the proposer's in-loop flush schedule. These tests
drive the real ``ChainSync.import_block`` on a file-backed SQLite store at
v24 and check two things:

* serial parity — the importer's final account/Transaction state equals the
  proposer-shaped apply (``apply_transaction_guarded`` + per-tx flush) for the
  same tx list;
* concurrency — N rounds of an import racing a rival seal of the same height
  on separate sessions never leave a torn state: exactly one Block at the
  height, every confirmed Transaction row belongs to it, and the sender
  nonce/balance reflect exactly one application of the tx list.

State-root validation is skipped (the point is persisted-state ordering, not
the root, which the golden corpus covers); the v20+ block hash is computed
over the delivered list so the importer's hash gate passes.
"""

from __future__ import annotations

import os
import random
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc_chain.base_models import Account, Block, Transaction
from aitbc_chain.config import settings as chain_settings
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.database import prod_parity_sessionmaker
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import StateTransition
from aitbc_chain.sync import ChainSync
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, create_engine, select

from .golden import profiles
from .test_importer_recipient_precreation import ADDR_A, ADDR_B, ADDR_NEW, CHAIN, KEY_A, _signed_tx

T0 = datetime(2026, 1, 1, tzinfo=UTC)
HEIGHT = 1
N_TXS = 6


@pytest.fixture(autouse=True)
def _v24_armed():
    snap = {a: getattr(chain_settings, a) for a in profiles.GATE_ATTRS}
    profiles.apply_profile(chain_settings, "gates1")
    yield
    for attr, val in snap.items():
        setattr(chain_settings, attr, val)


def _make_db(tmp_path, name: str):
    db_path = tmp_path / name / "chain.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 30})
    chain_metadata.create_all(engine)

    # Production session semantics: autoflush off, no commit on exit (the importer commits itself).
    factory = prod_parity_sessionmaker(engine)

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=0))
        session.add(Account(chain_id=CHAIN, address=ADDR_B, balance=0, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()
    return engine, factory


def _txs() -> list[dict[str, Any]]:
    return [
        _signed_tx(KEY_A, ADDR_A, i, amount=10 + i, to=ADDR_NEW if i % 2 else ADDR_B, tx_hash=f"0x{0x90 + i:02x}" + "ab" * 31)
        for i in range(N_TXS)
    ]


def _block(txs: list[dict[str, Any]], proposer_tag: str) -> dict[str, Any]:
    ts = (T0 + timedelta(seconds=60 * HEIGHT)).isoformat()
    parent = "0x" + "00" * 32
    proposer = ADDR_A
    h = compute_block_hash(CHAIN, HEIGHT, parent, ts, [t["tx_hash"] for t in txs], proposer, "", "", "")
    return {
        "chain_id": CHAIN,
        "height": HEIGHT,
        "hash": h,
        "parent_hash": parent,
        "proposer": proposer,
        "timestamp": ts,
        "tx_count": len(txs),
        "block_metadata": '{"state_transition_version": 24}',
        "signature": "",
        "transactions": txs,
        "_tag": proposer_tag,
    }


def _state(engine) -> dict[str, Any]:
    with Session(engine) as session:
        accts = {a.address: (a.balance, a.nonce) for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()}
        blocks = [(b.height, b.hash) for b in session.exec(select(Block).where(Block.chain_id == CHAIN)).all()]
        txrows = sorted(
            (t.tx_hash, t.block_height, t.status)
            for t in session.exec(select(Transaction).where(Transaction.chain_id == CHAIN)).all()
        )
    return {"accounts": accts, "blocks": sorted(blocks), "txs": txrows}


class SealRefused(Exception):
    """The rival seal's apply was refused because the other writer committed first."""


def _seal_proposer_shape(engine, txs: list[dict[str, Any]]) -> None:
    """The proposer's apply loop: apply, store the Transaction row, flush per tx, then the Block row."""
    st = StateTransition()
    with prod_parity_sessionmaker(engine)() as session:
        for tx in txs:
            data = dict(tx)
            data["value"] = data.get("amount", 0)
            ok, err = st.apply_transaction_guarded(
                session, CHAIN, data, data["tx_hash"], block_version=24, block_height=HEIGHT
            )
            if not ok:
                # Lost the race: the rival import already committed this tx.
                raise SealRefused(err)
            session.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash=data["tx_hash"],
                    block_height=HEIGHT,
                    sender=data["from"],
                    recipient=data["to"],
                    payload=data.get("payload", {}),
                    envelope=dict(data),
                    type="TRANSFER",
                    value=data["value"],
                    fee=data.get("fee", 0),
                    nonce=data["nonce"],
                    status="confirmed",
                )
            )
            session.flush()
        blk = _block(txs, "seal")
        session.add(
            Block(
                chain_id=CHAIN,
                height=HEIGHT,
                hash="0x" + "5e" * 32,
                parent_hash=blk["parent_hash"],
                proposer=ADDR_A,
                timestamp=T0 + timedelta(seconds=60 * HEIGHT),
                tx_count=len(txs),
            )
        )
        session.commit()


def _import(factory, txs: list[dict[str, Any]]):
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    blk = _block(txs, "import")
    blk.pop("_tag")
    return sync.import_block(blk, transactions=txs, skip_state_root_validation=True)


def test_serial_import_matches_proposer_shape(tmp_path):
    txs = _txs()
    p_engine, _ = _make_db(tmp_path, "prop")
    _seal_proposer_shape(p_engine, txs)
    i_engine, i_factory = _make_db(tmp_path, "imp")
    res = _import(i_factory, txs)
    assert res.accepted, res.reason
    prop, imp = _state(p_engine), _state(i_engine)
    assert imp["accounts"] == prop["accounts"]
    assert imp["txs"] == prop["txs"]
    assert len(imp["blocks"]) == 2  # genesis + height 1


ROUNDS = int(os.environ.get("FLUSH_STRESS_ROUNDS", "40"))


def _race(tmp_path, rnd: int, workers: list[str]):
    """Run one round: the named workers ("import"/"seal") released together on one store."""
    txs = _txs()
    engine, factory = _make_db(tmp_path, f"race{rnd}")
    barrier = threading.Barrier(len(workers))
    outcome: dict[str, Any] = {}
    rng = random.Random(rnd)
    delays = [rng.uniform(0.0, 0.06) if kind == "seal" else 0.0 for kind in workers]

    def run(idx: int, kind: str) -> None:
        key = f"{kind}{idx}"
        barrier.wait()
        # Deterministic per-round skew sweeps both orderings (the importer's
        # health/hash preamble is slower than a bare seal, so unskewed the
        # seal always wins).
        time.sleep(delays[idx])
        try:
            if kind == "import":
                res = _import(factory, [dict(t) for t in txs])
                outcome[key] = "accepted" if res.accepted else f"rejected:{res.reason}"
            else:
                _seal_proposer_shape(engine, [dict(t) for t in txs])
                outcome[key] = "sealed"
        except SealRefused as exc:
            outcome[key] = f"seal-refused:{exc}"
        except (OperationalError, IntegrityError) as exc:
            outcome[key] = f"db-refused:{type(exc).__name__}"
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            outcome[key] = f"CRASH:{type(exc).__name__}:{exc}"

    threads = [threading.Thread(target=run, args=(i, kind)) for i, kind in enumerate(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not any(t.is_alive() for t in threads), "worker hung"
    return engine, outcome


def _assert_consistent(engine, oracle: dict[str, Any], outcome: dict[str, Any]) -> None:
    crashes = {k: v for k, v in outcome.items() if v.startswith("CRASH")}
    assert not crashes, f"unhandled exception escaped a worker: {crashes}"
    state = _state(engine)
    at_height = [b for b in state["blocks"] if b[0] == HEIGHT]
    assert len(at_height) == 1, f"expected exactly one block at height {HEIGHT}, got {at_height} ({outcome})"
    assert state["accounts"] == oracle["accounts"], (
        f"torn/double apply: {state['accounts']} vs {oracle['accounts']} ({outcome})"
    )
    assert state["txs"] == oracle["txs"], f"tx rows differ from a single application ({outcome})"


@pytest.fixture()
def oracle(tmp_path):
    engine, factory = _make_db(tmp_path, "oracle")
    assert _import(factory, _txs()).accepted
    return _state(engine)


def test_import_races_rival_seal(tmp_path, oracle):
    wins = {"import": 0, "seal": 0}
    for rnd in range(ROUNDS):
        engine, outcome = _race(tmp_path, rnd, ["import", "seal"])
        _assert_consistent(engine, oracle, outcome)
        winner = [b for b in _state(engine)["blocks"] if b[0] == HEIGHT][0][1]
        wins["seal" if winner == "0x" + "5e" * 32 else "import"] += 1
    print("import-vs-seal winners:", wins)


def test_concurrent_duplicate_imports(tmp_path, oracle):
    for rnd in range(ROUNDS):
        engine, outcome = _race(tmp_path, rnd, ["import", "import", "import"])
        _assert_consistent(engine, oracle, outcome)
        assert any(v == "accepted" for v in outcome.values()), outcome
