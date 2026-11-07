"""R14-M1 (#1248): apply-rejected transactions must release their
(sender, nonce) mempool slot instead of squatting until mempool_entry_ttl.

Chain of custody pinned here:

- the proposer stamps apply-rejected identities into ``block_metadata``
  (``rejected_txs``) — outside the signed header and block hash;
- importers upsert sparse ``status='rejected'`` transaction rows and evict
  the dead entries from the local mempool;
- admission evicts a dead slot occupant so a replacement (any fee,
  including zero) takes the slot immediately;
- the RPC sweeper evicts pending entries whose hash has a rejected row,
  which is what frees the slot on services that never import blocks.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain import mempool as mempool_mod
from aitbc_chain.base_models import Account, Transaction
from aitbc_chain.config import settings
from aitbc_chain.database import chain_metadata
from aitbc_chain.mempool import compute_tx_hash, init_mempool
from aitbc_chain.models import Transaction as ModelsTransaction
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.sync_block_import import BlockImportMixin

CHAIN = "ait-test"
DEAD_HASH = "0x" + "ab" * 32
LIVE_HASH = "0x" + "cd" * 32
SENDER = "0x" + "5a" * 20


@pytest.fixture
def fresh_mempool():
    init_mempool("memory")
    yield mempool_mod.get_mempool()
    mempool_mod._MEMPOOL = None


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=SENDER, balance=1_000_000, nonce=0))
        s.commit()
        yield s


def _importer(chain_id: str = CHAIN) -> BlockImportMixin:
    obj = BlockImportMixin.__new__(BlockImportMixin)
    obj._chain_id = chain_id
    return obj


def _tx(nonce: int = 0, sender: str = SENDER, **overrides: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": sender,
        "to": "0x" + "ee" * 20,
        "amount": 0,
        "fee": 0,
        "nonce": nonce,
        "payload": {},
        "type": "TRANSFER",
        "chain_id": CHAIN,
        "signature": "0xsig",
    }
    tx.update(overrides)
    return tx


def _block_data(rejected: list[dict[str, Any]] | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"state_transition_version": 9}
    if rejected is not None:
        metadata["rejected_txs"] = rejected
    return {
        "height": 5,
        "hash": "0x" + "11" * 32,
        "parent_hash": "0x" + "22" * 32,
        "proposer": "0x" + "33" * 20,
        "block_metadata": json.dumps(metadata),
    }


# --- block_metadata parsing + import-side persistence -----------------------


def test_block_rejected_txs_parses_metadata():
    entries = [{"tx_hash": DEAD_HASH, "sender": SENDER, "nonce": 3, "reason": "bad nonce"}]
    assert BlockImportMixin._block_rejected_txs(_block_data(entries)) == entries


def test_block_rejected_txs_tolerates_garbage():
    for raw in (None, "", "not-json", json.dumps({"rejected_txs": "nope"}), json.dumps([1, 2])):
        data = _block_data(None)
        data["block_metadata"] = raw if raw is not None else None
        assert BlockImportMixin._block_rejected_txs(data) == []
    data = _block_data(None)
    data["block_metadata"] = json.dumps({"rejected_txs": [{"no_hash": 1}, {"tx_hash": DEAD_HASH}]})
    assert BlockImportMixin._block_rejected_txs(data) == [{"tx_hash": DEAD_HASH}]


def test_persist_import_rejections_writes_sparse_rows(session):
    entries = [{"tx_hash": DEAD_HASH, "sender": SENDER, "nonce": 3, "type": "transfer", "reason": "Invalid nonce"}]
    _importer()._persist_import_rejections(session, _block_data(entries))
    session.commit()

    row = session.exec(
        select(ModelsTransaction).where(ModelsTransaction.chain_id == CHAIN, ModelsTransaction.tx_hash == DEAD_HASH)
    ).first()
    assert row is not None
    assert row.status == "rejected"
    assert row.sender == SENDER
    assert row.nonce == 3
    assert row.type == "TRANSFER"
    assert row.block_height is None
    assert "proposer" in (row.tx_metadata or "")


def test_persist_import_rejections_upgrades_pending_but_not_confirmed(session):
    pending = Transaction(
        chain_id=CHAIN,
        tx_hash=DEAD_HASH,
        sender=SENDER,
        recipient="0x" + "ee" * 20,
        payload={},
        status="pending",
        nonce=3,
    )
    confirmed = Transaction(
        chain_id=CHAIN,
        tx_hash=LIVE_HASH,
        sender=SENDER,
        recipient="0x" + "ee" * 20,
        payload={},
        status="confirmed",
        nonce=4,
        block_height=4,
    )
    session.add(pending)
    session.add(confirmed)
    session.commit()

    entries = [
        {"tx_hash": DEAD_HASH, "sender": SENDER, "nonce": 3},
        {"tx_hash": LIVE_HASH, "sender": SENDER, "nonce": 4},
    ]
    _importer()._persist_import_rejections(session, _block_data(entries))
    session.commit()

    assert session.get(ModelsTransaction, pending.id).status == "rejected"
    assert session.get(ModelsTransaction, confirmed.id).status == "confirmed"


# --- mempool eviction on import ---------------------------------------------


def test_evicted_rejected_entries_free_the_slot(fresh_mempool):
    dead = _tx(nonce=0)
    dead_hash = fresh_mempool.add(dead, chain_id=CHAIN, tx_hash=DEAD_HASH)
    assert dead_hash == DEAD_HASH
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 0) == DEAD_HASH

    entries = [{"tx_hash": DEAD_HASH, "sender": SENDER, "nonce": 0, "reason": "Invalid nonce"}]
    _importer()._evict_rejected_from_mempool(_block_data(entries))

    assert fresh_mempool.list_transactions(CHAIN) == []
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 0) is None


def test_eviction_ignores_unrelated_entries(fresh_mempool):
    keep = _tx(nonce=7, sender="0x" + "77" * 20)
    fresh_mempool.add(keep, chain_id=CHAIN)
    entries = [{"tx_hash": DEAD_HASH, "sender": SENDER, "nonce": 0}]
    _importer()._evict_rejected_from_mempool(_block_data(entries))
    assert len(fresh_mempool.list_transactions(CHAIN)) == 1


def test_eviction_failure_never_propagates(fresh_mempool, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("mempool exploded")

    monkeypatch.setattr(mempool_mod, "get_mempool", _boom)
    entries = [{"tx_hash": DEAD_HASH, "sender": SENDER, "nonce": 0}]
    _importer()._evict_rejected_from_mempool(_block_data(entries))


# --- slot_occupant ------------------------------------------------------------


def test_slot_occupant_tracks_signed_entries(fresh_mempool):
    tx = _tx(nonce=2)
    tx_hash = fresh_mempool.add(tx, chain_id=CHAIN)
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 2) == tx_hash
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 3) is None
    fresh_mempool.remove(tx_hash, CHAIN)
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 2) is None


def test_slot_occupant_database_backend():
    init_mempool("database", db_url="sqlite://")
    try:
        mempool = mempool_mod.get_mempool()
        tx = _tx(nonce=5)
        tx_hash = mempool.add(tx, chain_id=CHAIN)
        assert mempool.slot_occupant(CHAIN, SENDER, 5) == tx_hash
        mempool.remove(tx_hash, CHAIN)
        assert mempool.slot_occupant(CHAIN, SENDER, 5) is None
    finally:
        mempool_mod._MEMPOOL = None


# --- admission: dead occupant release ---------------------------------------


@pytest.fixture
def door(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    return session


def _rejected_row(session: Session, tx_hash: str, sender: str = SENDER, nonce: int = 0) -> None:
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            sender=sender,
            recipient="",
            payload={},
            nonce=nonce,
            status="rejected",
        )
    )
    session.commit()


def test_admission_releases_dead_slot_occupant(door, fresh_mempool):
    dead = _tx(nonce=0, fee=0)
    dead_hash = compute_tx_hash(dead)
    fresh_mempool.add(dead, chain_id=CHAIN, tx_hash=dead_hash)
    _rejected_row(door, dead_hash)

    # A zero-fee replacement at the same slot must be admitted — the dead
    # occupant cannot command a fee premium it will never earn.
    replacement = _tx(nonce=0, fee=0, amount=1)
    _validate_transaction_admission(replacement, fresh_mempool)
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 0) is None
    fresh_mempool.add(replacement, chain_id=CHAIN)
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 0) == compute_tx_hash(replacement)


def test_admission_keeps_live_occupant_fee_rule(door, fresh_mempool):
    live = _tx(nonce=0, fee=5)
    live_hash = compute_tx_hash(live)
    fresh_mempool.add(live, chain_id=CHAIN, tx_hash=live_hash)

    cheap = _tx(nonce=0, fee=1, amount=1)
    _validate_transaction_admission(cheap, fresh_mempool)
    # Occupant is NOT dead — the strict-fee rule still applies at add() time.
    with pytest.raises(ValueError, match="already occupied"):
        fresh_mempool.add(cheap, chain_id=CHAIN)
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 0) == live_hash


def test_admission_ignores_rejected_rows_for_other_slots(door, fresh_mempool):
    dead = _tx(nonce=0, fee=0)
    dead_hash = compute_tx_hash(dead)
    fresh_mempool.add(dead, chain_id=CHAIN, tx_hash=dead_hash)
    # Rejected row exists but for a DIFFERENT slot's hash.
    _rejected_row(door, LIVE_HASH, nonce=9)
    live = _tx(nonce=0, fee=5)
    _validate_transaction_admission(live, fresh_mempool)
    assert fresh_mempool.slot_occupant(CHAIN, SENDER, 0) == dead_hash


# --- sweeper -----------------------------------------------------------------


def test_sweeper_evicts_rejected_pending_entries(session, fresh_mempool, monkeypatch):
    from aitbc_chain import app as app_mod

    dead = _tx(nonce=0)
    dead_hash = fresh_mempool.add(dead, chain_id=CHAIN)
    keep = _tx(nonce=1, sender="0x" + "77" * 20)
    fresh_mempool.add(keep, chain_id=CHAIN)
    _rejected_row(session, dead_hash)

    @contextmanager
    def _scope(chain_id: str = ""):
        yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", _scope)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "supported_chains", "")

    removed = app_mod._evict_rejected_mempool_entries()
    assert removed == 1
    remaining = fresh_mempool.pending_tx_hashes(CHAIN)
    assert dead_hash not in remaining
    assert len(remaining) == 1


def test_sweeper_no_pending_is_noop(session, monkeypatch):
    from aitbc_chain import app as app_mod

    @contextmanager
    def _scope(chain_id: str = ""):
        yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", _scope)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "supported_chains", "")
    assert app_mod._evict_rejected_mempool_entries() == 0


@pytest.mark.asyncio
async def test_import_block_rpc_wiring_persists_and_evicts(tmp_path, monkeypatch):
    """#1254 wiring pin: ``POST /rpc/importBlock`` must actually run the
    rejected-tx persistence and mempool eviction — not just define them.

    Drives the real ``rpc_blocks.import_block`` -> ``ChainSync.import_block``
    path against an isolated sqlite engine, with a signed block whose
    ``block_metadata`` carries ``rejected_txs``.
    """
    from contextlib import contextmanager as _cm
    from unittest.mock import Mock

    from eth_account import Account as EthAccount

    from aitbc.crypto.consensus_signing import sign_block_hash
    from aitbc_chain.models import Block as ModelsBlock
    from aitbc_chain.rpc import blocks as rpc_blocks

    db_path = tmp_path / "wiring.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    chain_metadata.create_all(engine)

    @_cm
    def _session_scope(*args: Any, **kwargs: Any):
        with Session(engine) as s:
            yield s

    monkeypatch.setattr(rpc_blocks, "session_scope", _session_scope)

    genesis_hash = "0x" + "00" * 32
    with Session(engine) as s:
        s.add(
            ModelsBlock(
                chain_id=CHAIN,
                height=0,
                hash=genesis_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=None,
                tx_count=0,
            )
        )
        s.commit()

    proposer = EthAccount.create()
    block_hash = "0x" + "11" * 32
    rejected_entry = {"tx_hash": DEAD_HASH, "sender": SENDER, "nonce": 0, "type": "TRANSFER", "reason": "pin"}
    block_data = {
        "chain_id": CHAIN,
        "height": 1,
        "hash": block_hash,
        "parent_hash": genesis_hash,
        "proposer": proposer.address,
        "timestamp": "2026-01-01T00:01:00+00:00",
        "tx_count": 0,
        "signature": sign_block_hash(block_hash, proposer.key.hex()),
        "block_metadata": json.dumps({"rejected_txs": [rejected_entry]}),
    }

    fake_mempool = Mock()
    fake_mempool.remove.return_value = True
    monkeypatch.setattr(mempool_mod, "get_mempool", lambda: fake_mempool)

    result = await rpc_blocks.import_block(Mock(), block_data)

    assert result["success"] is True and result["accepted"] is True
    with Session(engine) as s:
        row = s.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == DEAD_HASH)).first()
    assert row is not None and row.status == "rejected"
    fake_mempool.remove.assert_called_once_with(DEAD_HASH, CHAIN)
    engine.dispose()


@pytest.mark.asyncio
async def test_sweeper_loop_invokes_rejected_eviction(fresh_mempool, monkeypatch):
    """#1254 wiring pin: ``_sweep_mempool_forever`` must actually call
    ``_evict_rejected_mempool_entries`` each tick — the sweeper tests above
    only prove the helper works when invoked directly."""
    import asyncio

    from aitbc_chain import app as app_mod

    calls = []
    monkeypatch.setattr(app_mod, "_evict_rejected_mempool_entries", lambda: calls.append(1) or 0)

    ticks = {"n": 0}

    async def _fake_sleep(_interval: float) -> None:
        ticks["n"] += 1
        if ticks["n"] > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await app_mod._sweep_mempool_forever()
    assert calls == [1]
