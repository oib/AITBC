"""#2649: hub1 ``/rpc/pending`` retained sealed/dead protocol txs indefinitely.

Two defects pinned here:

- ``DatabaseMempool.evict_expired`` reduced every stale hash to ``"0"`` —
  ``session.exec(select(col))`` yields scalars, not rows, so the ``r[0]``
  unpack produced ``tx_hash.in_(["0", ...])`` which matches nothing. TTL
  eviction never fired on the database backend.
- ``_reconcile_sealed_mempool_entries`` matched pending rows to sealed
  ``Transaction`` rows by ``tx_hash`` only. Unsigned protocol writes pool
  under their admission hash; the proposer rewrites the envelope at seal
  time (``signature``/``value``/``tx_hash`` fields), so the chain records
  a different hash and the sweep never matched them.
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, update

from aitbc_chain import mempool as mempool_mod
from aitbc_chain.app import (
    _pending_sealed_twin_key,
    _reconcile_sealed_mempool_entries,
    _sealed_tx_twin_key,
)
from aitbc_chain.base_models import Transaction
from aitbc_chain.config import settings
from aitbc_chain.database import chain_metadata
from aitbc_chain.mempool import DatabaseMempool, compute_tx_hash, init_mempool
from aitbc_chain.mempool_common import MempoolEntry

CHAIN = "twin-" + uuid.uuid4().hex[:8]
SENDER = "0x" + "5a" * 20
RECIPIENT = "0x" + "ee" * 20
SEALED_HASH = "0x" + "1b" * 32


def _protocol_tx(**overrides: Any) -> dict[str, Any]:
    """Unsigned protocol write — signature lives in ``payload.auth``."""
    tx: dict[str, Any] = {
        "from": SENDER,
        "to": RECIPIENT,
        "amount": 36_000_000,
        "fee": 0,
        "nonce": 58,
        "payload": {
            "agent_stake_id": "agent-stake-test",
            "auth": {"signer": SENDER, "signature": "0xsig"},
            "lock_days": 1,
        },
        "type": "STAKE_LOCK",
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


@pytest.fixture
def db_pool(tmp_path):
    url = os.environ.get("Q2649_PG_URL") or f"sqlite:///{tmp_path / 'mempool.db'}"
    p = DatabaseMempool(url, max_size=100, min_fee=0)
    yield p
    p._engine.dispose()


@pytest.fixture
def chain_id() -> str:
    return "evict-" + uuid.uuid4().hex[:8]


# --- evict_expired scalar bug -------------------------------------------------


def test_db_evict_expired_removes_stale_rows(db_pool, chain_id):
    """Regression pin: r[0] on a scalar result reduced hashes to '0'."""
    txs = [
        {
            "from": SENDER,
            "to": RECIPIENT,
            "amount": 1,
            "fee": 0,
            "nonce": i,
            "payload": {},
            "type": "TRANSFER",
            "chain_id": chain_id,
            "signature": "0xsig",
        }
        for i in range(3)
    ]
    for tx in txs:
        db_pool.add(tx, chain_id=chain_id)
    assert db_pool.size(chain_id) == 3

    # Age every row past the TTL, then sweep — all three must go.
    old = time.time() - 7200
    with Session(db_pool._engine) as session:
        session.exec(update(MempoolEntry).where(MempoolEntry.chain_id == chain_id).values(received_at=old))
        session.commit()

    assert db_pool.evict_expired(3600) == 3
    assert db_pool.size(chain_id) == 0


def test_db_evict_expired_keeps_fresh_rows(db_pool, chain_id):
    db_pool.add(
        {
            "from": SENDER,
            "to": RECIPIENT,
            "amount": 1,
            "fee": 0,
            "nonce": 0,
            "payload": {},
            "type": "TRANSFER",
            "chain_id": chain_id,
            "signature": "0xsig",
        },
        chain_id=chain_id,
    )
    assert db_pool.evict_expired(3600) == 0
    assert db_pool.size(chain_id) == 1


# --- sealed-twin key helpers ---------------------------------------------------


def test_pending_twin_key_unsigned_protocol_only():
    assert _pending_sealed_twin_key(_protocol_tx()) is not None
    # Signed entries keep their hash through sealing — not twin candidates.
    assert _pending_sealed_twin_key(_protocol_tx(signature="0xtop")) is None
    # Payload-less transfers could collide with an identical payment.
    assert _pending_sealed_twin_key(_protocol_tx(payload={})) is None
    assert _pending_sealed_twin_key(_protocol_tx(payload="nope")) is None
    no_sender = _protocol_tx()
    no_sender["from"] = ""
    assert _pending_sealed_twin_key(no_sender) is None


def test_sealed_twin_key_matches_pending_fields():
    row = Transaction(
        chain_id=CHAIN,
        tx_hash=SEALED_HASH,
        sender=SENDER,
        recipient=RECIPIENT,
        type="STAKE_LOCK",
        value=36_000_000,
        nonce=58,
        payload=_protocol_tx()["payload"],
        status="confirmed",
        block_height=99,
    )
    assert _sealed_tx_twin_key(row) == _pending_sealed_twin_key(_protocol_tx())
    # Nonce is deliberately absent from the key — the proposer may rewrite it.
    row.nonce = 1
    assert _sealed_tx_twin_key(row) == _pending_sealed_twin_key(_protocol_tx())
    # Payload divergence breaks the match.
    row.payload = {"agent_stake_id": "other"}
    assert _sealed_tx_twin_key(row) != _pending_sealed_twin_key(_protocol_tx())


# --- _reconcile_sealed_mempool_entries twin leg --------------------------------


@pytest.fixture
def chain_session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "supported_chains", "")

    @contextmanager
    def _scope(chain_id: str):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", _scope)
    yield engine


def _confirmed_tx(session: Session, tx: dict[str, Any], *, tx_hash: str = SEALED_HASH, block_height: int = 99) -> None:
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            sender=tx["from"],
            recipient=tx["to"],
            type=tx["type"],
            value=tx["amount"],
            nonce=tx["nonce"],
            payload=tx["payload"],
            status="confirmed",
            block_height=block_height,
        )
    )
    session.commit()


def test_reconcile_evicts_hash_mutated_protocol_twin(chain_session):
    init_mempool("memory")
    pool = mempool_mod.get_mempool()
    try:
        pending = _protocol_tx()
        pool.add(pending, chain_id=CHAIN)
        admission_hash = compute_tx_hash(pending)
        assert admission_hash != SEALED_HASH

        with Session(chain_session) as session:
            _confirmed_tx(session, pending)

        removed = _reconcile_sealed_mempool_entries()
        assert removed == 1
        assert pool.pending_tx_hashes(CHAIN) == set()
    finally:
        mempool_mod._MEMPOOL = None


def test_reconcile_keeps_pending_when_no_sealed_twin(chain_session):
    init_mempool("memory")
    pool = mempool_mod.get_mempool()
    try:
        pending = _protocol_tx()
        pool.add(pending, chain_id=CHAIN)

        # Confirmed row with a *different* payload is not the twin.
        other = _protocol_tx(payload={"agent_stake_id": "agent-stake-other"})
        with Session(chain_session) as session:
            _confirmed_tx(session, other)

        assert _reconcile_sealed_mempool_entries() == 0
        assert pool.pending_tx_hashes(CHAIN) == {compute_tx_hash(pending)}
    finally:
        mempool_mod._MEMPOOL = None


def test_reconcile_ignores_signed_and_payloadless_pending(chain_session):
    init_mempool("memory")
    pool = mempool_mod.get_mempool()
    try:
        signed = _protocol_tx(signature="0xtop")
        pool.add(signed, chain_id=CHAIN)
        bare = _protocol_tx(payload={}, type="TRANSFER")
        pool.add(bare, chain_id=CHAIN)

        with Session(chain_session) as session:
            _confirmed_tx(session, signed)
            _confirmed_tx(session, bare, tx_hash="0x" + "2c" * 32)

        assert _reconcile_sealed_mempool_entries() == 0
        assert len(pool.pending_tx_hashes(CHAIN)) == 2
    finally:
        mempool_mod._MEMPOOL = None
