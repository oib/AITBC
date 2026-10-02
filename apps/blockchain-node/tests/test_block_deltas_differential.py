"""Differential undo proof — one test per transaction family.

The account state-root check in ``revert_losing_segment`` only covers the
``account`` table; everything else a transaction writes (escrow, GPU
registrations, bonds, chain parameters, transaction rows, market payloads)
is proven here instead: snapshot EVERY chain table, apply a real signed
transaction inside a journaled block the way ``_append_block`` does, revert
the block, snapshot again. The two dumps must be identical — any table the
journal misses leaves a row (or a changed field) behind and fails the diff.

A test also asserts the journal came out ``complete`` and the mid-apply dump
differed from the pre-apply one, so a silently-rejected transaction cannot
masquerade as a passing round-trip.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import (
    Account,
    Block,
    ChainParameter,
    LiquidityPool,
    LiquidityStake,
    Receipt,
)
from aitbc_chain.base_models import Transaction as ChainTransaction
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state.block_deltas import (
    BlockDeltaJournal,
    journal_status,
    revert_losing_segment,
)
from aitbc_chain.state.bridge_credit import sign_bridge_credit
from aitbc_chain.state.gpu_resources import GPURegistration
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import (
    StateTransition,
    _BOND_BURN_ADDRESS,
    _BOND_ESCROW_ADDRESS,
)
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

CHAIN = "diff-chain"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
BLOCK_VERSION = 7

BUYER_KEY = "0x" + "11" * 32
PROVIDER_KEY = "0x" + "22" * 32
AUTH_KEY = "0x" + "33" * 32  # settlement/slash/governance authority
MARKET_A_KEY = "0x" + "44" * 32
MARKET_B_KEY = "0x" + "55" * 32

BUYER = derive_ethereum_address(BUYER_KEY)
PROVIDER = derive_ethereum_address(PROVIDER_KEY)
AUTH = derive_ethereum_address(AUTH_KEY)
MARKET_A = derive_ethereum_address(MARKET_A_KEY)
MARKET_B = derive_ethereum_address(MARKET_B_KEY)
NODE_WALLET = derive_ethereum_address("0x" + "66" * 32)


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture(autouse=True)
def _clean_authority_env(monkeypatch):
    """No env authority leakage — the tests seed every gate on-chain."""
    monkeypatch.setattr(settings, "bridge_release_authority", "")
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.delenv("BRIDGE_RELEASE_AUTHORITY", raising=False)
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.delenv("ESCROW_SETTLEMENT_AUTHORITY", raising=False)
    monkeypatch.delenv("BOND_SLASH_AUTHORITY_ADDRESS", raising=False)


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'diff.db'}", echo=False)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    @contextmanager
    def _factory():
        with Session(db_engine) as session:
            yield session

    return _factory


# --------------------------------------------------------------------------
# signed transaction builders
# --------------------------------------------------------------------------


def _sign_data(private_key: str, data: dict) -> str:
    from eth_utils import keccak

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _make_tx(private_key: str, tx_data: dict) -> dict:
    tx = dict(tx_data)
    tx["from"] = derive_ethereum_address(private_key)
    tx.setdefault("to", tx["from"])
    signable = {k: v for k, v in tx.items() if k != "signature"}
    if "amount" in signable:
        signable.pop("value", None)
    tx["signature"] = _sign_data(private_key, signable)
    return tx


def _hash(*parts: object) -> str:
    return "0x" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


# --------------------------------------------------------------------------
# snapshot / apply / revert harness
# --------------------------------------------------------------------------


def _snapshot(db_engine) -> dict[str, list[str]]:
    """Every chain table -> sorted list of its rows, JSON-normalised.

    Row order is irrelevant (sorted), so the diff is pure set equality on
    every column of every chain table — including ``block_state_delta`` itself
    (a clean revert deletes the reverted block's own delta rows).
    """
    out: dict[str, list[str]] = {}
    with Session(db_engine) as session:
        for name, table in chain_metadata.tables.items():
            rows = session.execute(table.select()).mappings().all()
            out[name] = sorted(json.dumps(dict(r), sort_keys=True, default=str) for r in rows)
    return out


def _mk_block_row(session: Session, height: int, parent_hash: str, tx_count: int) -> None:
    session.add(
        Block(
            chain_id=CHAIN,
            height=height,
            hash=_hash("block", height, parent_hash),
            parent_hash=parent_hash,
            proposer="proposer-a",
            timestamp=T0 + timedelta(seconds=30 * height),
            tx_count=tx_count,
            state_root=None,
        )
    )


def _apply_block(
    session_factory, height: int, parent_hash: str, txs: list[dict], *, block_version: int = BLOCK_VERSION
) -> None:
    """Apply one block exactly the way _append_block does: journal attached,
    each tx through apply_transaction, a confirmed Transaction row carrying
    its signed envelope, journal persisted inside the same commit, and the
    block's state_root stamped with the post-apply root."""
    st = StateTransition()
    with session_factory() as session:
        journal = BlockDeltaJournal.attach(session, CHAIN, height)
        _mk_block_row(session, height, parent_hash, tx_count=len(txs))
        for i, tx in enumerate(txs):
            tx_hash = str(tx.get("tx_hash") or _hash("tx", height, i))
            ok, msg = st.apply_transaction(session, CHAIN, tx, tx_hash, block_version=block_version, block_height=height)
            assert ok, f"{tx.get('type')} failed to apply: {msg}"
            session.add(
                ChainTransaction(
                    chain_id=CHAIN,
                    tx_hash=tx_hash,
                    block_height=height,
                    sender=tx.get("from", ""),
                    recipient=tx.get("to", ""),
                    payload=tx.get("payload") if isinstance(tx.get("payload"), dict) else {},
                    envelope=dict(tx),
                    type=tx.get("type", "TRANSFER"),
                    value=tx.get("value", tx.get("amount", 0)),
                    fee=tx.get("fee", 0),
                    nonce=tx.get("nonce", 0),
                    status="confirmed",
                )
            )
        blk = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == height)).one()
        blk.state_root = compute_state_root_full(session, CHAIN)
        journal.persist(session)
        session.commit()
    with session_factory() as session:
        assert journal_status(session, CHAIN, height) == "complete", (
            f"block {height} journal came out incomplete — a capture fired that "
            "the differential test must either model or treat as a real gap"
        )


def _revert_block(session_factory, height: int, ancestor_height: int) -> None:
    with session_factory() as session:
        ours = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == height)).one()
        anc = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == ancestor_height)).one()
        provably_empty = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)._blocks_provably_empty
        payloads = revert_losing_segment(session, CHAIN, [ours], anc, provably_empty)
        assert payloads is not None, f"revert of block {height} refused — journal incomplete or root mismatch"
        session.commit()


def _roundtrip(session_factory, db_engine, height: int, parent_hash: str, ancestor_height: int, txs: list[dict]) -> None:
    """Snapshot → apply → (mutated, journal complete) → revert → identical."""
    before = _snapshot(db_engine)
    _apply_block(session_factory, height, parent_hash, txs)
    mid = _snapshot(db_engine)
    assert mid != before, "the transaction changed no chain table — the test proves nothing"
    _revert_block(session_factory, height, ancestor_height)
    after = _snapshot(db_engine)
    assert after == before, _dump_diff(before, after)


def _dump_diff(before: dict[str, list[str]], after: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for table in sorted(set(before) | set(after)):
        b, a = set(before.get(table, [])), set(after.get(table, []))
        if b == a:
            continue
        missing = b - a  # rows present before apply, absent after revert
        extra = a - b  # rows the revert left behind / mutated
        parts.append(f"table {table}:")
        for row in sorted(missing):
            parts.append(f"  - lost row: {row[:400]}")
        for row in sorted(extra):
            parts.append(f"  + leftover/mutated row: {row[:400]}")
    return "\n".join(parts) or "snapshots differ"


# --------------------------------------------------------------------------
# seeding helpers
# --------------------------------------------------------------------------


def _mk_block_dict(height: int, parent_hash: str) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": _hash("block", height, parent_hash),
        "parent_hash": parent_hash,
        "proposer": "proposer-a",
        "timestamp": (T0 + timedelta(seconds=30 * height)).isoformat(),
        "tx_count": 0,
        "state_root": None,
    }


def _store_block(session_factory, height: int, parent_hash: str) -> dict[str, Any]:
    blk = _mk_block_dict(height, parent_hash)
    with session_factory() as session:
        _mk_block_row(session, height, parent_hash, 0)
        session.commit()
    return blk


def _stamp_root(session_factory, height: int) -> str | None:
    with session_factory() as session:
        root = compute_state_root_full(session, CHAIN)
        blk = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == height)).one()
        blk.state_root = root
        session.commit()
    return root


def _fund(session_factory, *addrs: str, balance: int = 1_000_000) -> None:
    with session_factory() as session:
        for addr in addrs:
            session.add(Account(chain_id=CHAIN, address=addr, balance=balance, nonce=0))
        session.commit()


def _set_param(session_factory, name: str, value: str) -> None:
    with session_factory() as session:
        session.add(ChainParameter(chain_id=CHAIN, parameter=name, value=value))
        session.commit()


def _seeded_ancestor(session_factory, height: int = 0, parent_hash: str = "0x00") -> dict[str, Any]:
    """Store the ancestor block AFTER all seeds, stamped with the real root —
    the revert verifier recomputes against this."""
    blk = _store_block(session_factory, height, parent_hash)
    _stamp_root(session_factory, height)
    return blk


def _genesis() -> dict[str, Any]:
    return _mk_block_dict(0, "0x00")


# --------------------------------------------------------------------------
# transaction families
# --------------------------------------------------------------------------


class TestTransferFamily:
    def test_transfer(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": PROVIDER,
                "amount": 5000,
                "value": 5000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "TRANSFER",
                "chain_id": CHAIN,
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])


class TestGpuMarketFamily:
    """GPU_MARKET is value-zero: market state derives from the transaction
    rows themselves, so the journal only has to restore account + tx rows.
    Run the common action variants in one block."""

    def test_gpu_market_offer_and_bid(self, session_factory, db_engine):
        _fund(session_factory, MARKET_A, MARKET_B)
        anc = _seeded_ancestor(session_factory)
        offer = _make_tx(
            MARKET_A_KEY,
            {
                "to": MARKET_A,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GPU_MARKET",
                "chain_id": CHAIN,
                "payload": {
                    "action": "offer",
                    "offer_id": "offer-1",
                    "gpu_id": "gpu-1",
                    "price_per_hour": "0.25",
                },
            },
        )
        bid = _make_tx(
            MARKET_B_KEY,
            {
                "to": MARKET_B,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GPU_MARKET",
                "chain_id": CHAIN,
                "payload": {
                    "action": "software_offer",
                    "offer_id": "sw-1",
                    "app": "ffmpeg",
                    "price": "0.05",
                },
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [offer, bid])


class TestGpuRegisterFamily:
    def test_gpu_register(self, session_factory, db_engine):
        _fund(session_factory, PROVIDER)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            PROVIDER_KEY,
            {
                "to": PROVIDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GPU_REGISTER",
                "chain_id": CHAIN,
                "payload": {
                    "gpu_id": "gpu-rt1",
                    "miner_id": "miner-rt1",
                    "model": "RTX 4090",
                    "memory_gb": 24,
                    "price_per_hour": "0.1",
                },
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])


class TestEscrowFamily:
    """S-4 path (v3+): the lock funds a deterministic per-escrow address; the
    release/refund then moves value out of it through four raw account writes
    plus the generic debit/credit — the heaviest raw-SQL shape in the apply
    path."""

    def _lock_tx(self, nonce: int = 0) -> dict:
        return _make_tx(
            BUYER_KEY,
            {
                "to": NODE_WALLET,
                "amount": 7000,
                "value": 7000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": nonce,
                "type": "ESCROW_LOCK",
                "chain_id": CHAIN,
                "payload": {"job_id": "job-esc-1", "provider": PROVIDER},
            },
        )

    def test_escrow_lock(self, session_factory, db_engine):
        _fund(session_factory, BUYER, NODE_WALLET)
        anc = _seeded_ancestor(session_factory)
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [self._lock_tx()])

    def _setup_locked_job(self, session_factory) -> dict[str, Any]:
        """Committed block 1 carries the lock; the authority param lets the
        release/refund validate at v7. Returns the block-1 dict (ancestor)."""
        _fund(session_factory, BUYER, NODE_WALLET, AUTH)
        _set_param(session_factory, "escrow_settlement_authority", AUTH)
        genesis = _store_block(session_factory, 0, "0x00")
        _stamp_root(session_factory, 0)
        _apply_block(session_factory, 1, genesis["hash"], [self._lock_tx()])
        return _mk_block_dict(1, genesis["hash"]) | {"hash": _hash("block", 1, genesis["hash"])}

    def test_escrow_release(self, session_factory, db_engine):
        lock_block = self._setup_locked_job(session_factory)
        release = _make_tx(
            AUTH_KEY,
            {
                "to": PROVIDER,  # beneficiary per the sealed lock
                "amount": 7000,
                "value": 7000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "ESCROW_RELEASE",
                "chain_id": CHAIN,
                "payload": {"job_id": "job-esc-1"},
            },
        )
        _roundtrip(session_factory, db_engine, 2, lock_block["hash"], 1, [release])

    def test_escrow_refund(self, session_factory, db_engine):
        lock_block = self._setup_locked_job(session_factory)
        refund = _make_tx(
            AUTH_KEY,
            {
                "to": BUYER,  # refund pays the lock's sender
                "amount": 7000,
                "value": 7000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "ESCROW_REFUND",
                "chain_id": CHAIN,
                "payload": {"job_id": "job-esc-1"},
            },
        )
        _roundtrip(session_factory, db_engine, 2, lock_block["hash"], 1, [refund])


class TestBridgeFamily:
    """Bridge credits carry the internal pseudo-sender plus the authority's
    bridge_signature (v5+); the refund additionally names its sealed lock
    (v6)."""

    def _setup_authority(self, session_factory) -> None:
        _set_param(session_factory, "bridge_release_authority", AUTH)

    def test_bridge_lock(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        lock = _make_tx(
            BUYER_KEY,
            {
                "to": "bridge_lock",
                "amount": 9000,
                "value": 9000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "BRIDGE_LOCK",
                "chain_id": CHAIN,
                "payload": {
                    "transfer_id": "xfer-1",
                    "target_chain": "ait-side",
                    "target_recipient": PROVIDER,
                    "asset": "AIT",
                },
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [lock])

    def test_bridge_release(self, session_factory, db_engine):
        _fund(session_factory, PROVIDER)
        self._setup_authority(session_factory)
        anc = _seeded_ancestor(session_factory)
        release = {
            "from": "bridge_release",
            "to": PROVIDER,
            "amount": 4321,
            "value": 4321,
            "fee": 0,
            "nonce": 0,
            "type": "BRIDGE_RELEASE",
            "chain_id": CHAIN,
            "payload": {"transfer_id": "xfer-9", "asset": "AIT"},
            "tx_hash": _hash("bridge-release", "xfer-9"),
        }
        release["payload"]["bridge_signature"] = sign_bridge_credit(release, release["tx_hash"], AUTH_KEY)
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [release])

    def test_bridge_refund(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        self._setup_authority(session_factory)
        genesis = _store_block(session_factory, 0, "0x00")
        _stamp_root(session_factory, 0)
        # Block 1 seals the lock the refund will name.
        lock = _make_tx(
            BUYER_KEY,
            {
                "to": "bridge_lock",
                "amount": 9000,
                "value": 9000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "BRIDGE_LOCK",
                "chain_id": CHAIN,
                "payload": {"transfer_id": "xfer-1", "target_chain": "ait-side"},
                "tx_hash": _hash("bridge-lock", "xfer-1"),
            },
        )
        _apply_block(session_factory, 1, genesis["hash"], [lock])
        lock_hash = lock["tx_hash"]

        refund = {
            "from": "bridge_refund",
            "to": BUYER,
            "amount": 9000,
            "value": 9000,
            "fee": 0,
            "nonce": 0,
            "type": "BRIDGE_REFUND",
            "chain_id": CHAIN,
            "payload": {"lock_tx_hash": lock_hash, "amount": 9000, "reason": "target_failed"},
            "tx_hash": _hash("bridge-refund", "xfer-1"),
        }
        refund["payload"]["bridge_signature"] = sign_bridge_credit(refund, refund["tx_hash"], AUTH_KEY)
        _roundtrip(session_factory, db_engine, 2, _hash("block", 1, genesis["hash"]), 1, [refund])


class TestBondFamily:
    def test_bond_lock(self, session_factory, db_engine):
        _fund(session_factory, PROVIDER, _BOND_ESCROW_ADDRESS)
        anc = _seeded_ancestor(session_factory)
        lock = _make_tx(
            PROVIDER_KEY,
            {
                "to": _BOND_ESCROW_ADDRESS,
                "amount": 5000,
                "value": 5000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "BOND_LOCK",
                "chain_id": CHAIN,
                "payload": {"bond_id": "bond-1", "provider": PROVIDER, "lock_days": 7},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [lock])

    def _setup_bond(self, session_factory, *, lock_days: int = 7) -> dict[str, Any]:
        _fund(session_factory, PROVIDER, _BOND_ESCROW_ADDRESS)
        genesis = _store_block(session_factory, 0, "0x00")
        _stamp_root(session_factory, 0)
        lock = _make_tx(
            PROVIDER_KEY,
            {
                "to": _BOND_ESCROW_ADDRESS,
                "amount": 5000,
                "value": 5000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "BOND_LOCK",
                "chain_id": CHAIN,
                "payload": {"bond_id": "bond-1", "provider": PROVIDER, "lock_days": lock_days},
            },
        )
        _apply_block(session_factory, 1, genesis["hash"], [lock])
        return genesis

    def test_bond_release(self, session_factory, db_engine):
        # lock_days=-1 → locked_until already past → releasable.
        genesis = self._setup_bond(session_factory, lock_days=-1)
        release = _make_tx(
            PROVIDER_KEY,
            {
                "to": PROVIDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 1,
                "type": "BOND_RELEASE",
                "chain_id": CHAIN,
                "payload": {"bond_id": "bond-1", "provider": PROVIDER},
            },
        )
        _roundtrip(session_factory, db_engine, 2, _hash("block", 1, genesis["hash"]), 1, [release])

    def test_bond_slash(self, session_factory, db_engine):
        genesis = self._setup_bond(session_factory)
        _fund(session_factory, AUTH)
        _set_param(session_factory, "bond_slash_authority", AUTH)
        # The authority seed lands after block 1 — re-stamp the ancestor root.
        _stamp_root(session_factory, 1)
        slash = _make_tx(
            AUTH_KEY,
            {
                "to": _BOND_BURN_ADDRESS,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "BOND_SLASH",
                "chain_id": CHAIN,
                "payload": {"bond_id": "bond-1", "provider": PROVIDER, "amount": 2000},
            },
        )
        _roundtrip(session_factory, db_engine, 2, _hash("block", 1, genesis["hash"]), 1, [slash])


class TestGovernanceFamily:
    def test_governance_parameter_change(self, session_factory, db_engine):
        _fund(session_factory, AUTH)
        _set_param(session_factory, "governance_executors", AUTH)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            AUTH_KEY,
            {
                "to": AUTH,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GOVERNANCE_EXECUTE",
                "chain_id": CHAIN,
                "payload": {
                    "proposal_id": "prop-diff-1",
                    "execution_payload": {
                        "action": "parameter_change",
                        "parameter": "market_fee_bps",
                        "value": "250",
                    },
                },
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])


class TestMessageFamily:
    def test_message(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": PROVIDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "MESSAGE",
                "chain_id": CHAIN,
                "payload": {"text": "hello chain"},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])


class TestGpuAllocateFamily:
    """GPU_ALLOCATE inserts a gpu_allocation row against an existing
    registration — the registration is committed by a prior journaled block."""

    def test_gpu_allocate(self, session_factory, db_engine):
        _fund(session_factory, PROVIDER, BUYER)
        genesis = _store_block(session_factory, 0, "0x00")
        _stamp_root(session_factory, 0)
        register = _make_tx(
            PROVIDER_KEY,
            {
                "to": PROVIDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GPU_REGISTER",
                "chain_id": CHAIN,
                "payload": {
                    "gpu_id": "gpu-alloc-1",
                    "miner_id": "miner-alloc-1",
                    "model": "RTX 4090",
                    "memory_gb": 24,
                    "price_per_hour": "0.1",
                },
            },
        )
        _apply_block(session_factory, 1, genesis["hash"], [register])
        allocate = _make_tx(
            BUYER_KEY,
            {
                "to": BUYER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GPU_ALLOCATE",
                "chain_id": CHAIN,
                "payload": {
                    "gpu_id": "gpu-alloc-1",
                    "allocation_id": "alloc-1",
                    "client_id": "client-1",
                    "duration_hours": 2.0,
                    "total_cost": "0.2",
                },
            },
        )
        _roundtrip(session_factory, db_engine, 2, _hash("block", 1, genesis["hash"]), 1, [allocate])


class TestGpuDeregisterFamily:
    """GPU_DEREGISTER (v10) updates an existing gpu_registration row to ``deactivated``; the undo journal must put
    the row back exactly as the registering block left it."""

    def test_gpu_deregister_rolls_back(self, session_factory, db_engine):
        _fund(session_factory, PROVIDER)
        genesis = _store_block(session_factory, 0, "0x00")
        _stamp_root(session_factory, 0)
        register = _make_tx(
            PROVIDER_KEY,
            {
                "to": PROVIDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GPU_REGISTER",
                "chain_id": CHAIN,
                "payload": {
                    "gpu_id": "gpu-dereg-1",
                    "miner_id": "miner-dereg-1",
                    "model": "RTX 4090",
                    "memory_gb": 24,
                    "price_per_hour": "0.1",
                },
            },
        )
        _apply_block(session_factory, 1, genesis["hash"], [register])
        deregister = _make_tx(
            PROVIDER_KEY,
            {
                "to": PROVIDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 1,
                "type": "GPU_DEREGISTER",
                "chain_id": CHAIN,
                "payload": {"gpu_id": "gpu-dereg-1"},
            },
        )

        def status() -> str:
            with session_factory() as session:
                row = session.exec(select(GPURegistration).where(GPURegistration.gpu_id == "gpu-dereg-1")).one()
                return row.status

        before = _snapshot(db_engine)
        assert status() == "active"
        _apply_block(session_factory, 2, _hash("block", 1, genesis["hash"]), [deregister], block_version=10)
        assert status() == "deactivated"
        assert _snapshot(db_engine) != before
        _revert_block(session_factory, 2, 1)
        assert status() == "active"
        after = _snapshot(db_engine)
        assert after == before, _dump_diff(before, after)


class TestIpfsSubscriptionFamily:
    """Insert and extend (update) of ipfs_subscription rows."""

    def _sub_tx(self, nonce: int) -> dict:
        return _make_tx(
            BUYER_KEY,
            {
                "to": BUYER,
                "amount": 100,
                "value": 100,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": nonce,
                "type": "IPFS_SUBSCRIPTION",
                "chain_id": CHAIN,
                "payload": {"island_id": "island-1", "duration_blocks": 100, "quota_bytes": 2048},
            },
        )

    def test_ipfs_subscription_insert(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [self._sub_tx(0)])

    def test_ipfs_subscription_extend(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        genesis = _store_block(session_factory, 0, "0x00")
        _stamp_root(session_factory, 0)
        _apply_block(session_factory, 1, genesis["hash"], [self._sub_tx(0)])
        _roundtrip(session_factory, db_engine, 2, _hash("block", 1, genesis["hash"]), 1, [self._sub_tx(1)])


class TestBridgeWithdrawFamily:
    def test_bridge_withdraw(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": "bridge_burn",
                "amount": 3000,
                "value": 3000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "BRIDGE_WITHDRAW",
                "chain_id": CHAIN,
                "payload": {"eth_address": derive_ethereum_address("0x" + "77" * 32)},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])


class TestReceiptClaimFamily:
    def test_receipt_claim(self, session_factory, db_engine):
        _fund(session_factory, PROVIDER)
        receipt_id = _hash("receipt", "job-1")
        with session_factory() as session:
            session.add(
                Receipt(
                    chain_id=CHAIN,
                    job_id="job-1",
                    receipt_id=receipt_id,
                    payload={"units": 12},
                    miner_signature={"sig": "miner"},
                    coordinator_attestations=[{"att": "coord"}],
                    minted_amount=1234,
                    status="pending",
                )
            )
            session.commit()
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            PROVIDER_KEY,
            {
                "to": PROVIDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "RECEIPT_CLAIM",
                "chain_id": CHAIN,
                "payload": {"receipt_id": receipt_id},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])


class TestLiquidityFamily:
    """Liquidity rows live in liquidity_pool/liquidity_stake plus pool
    accounts — raw account writes and ORM rows both under the journal."""

    def test_liquidity_deposit(self, session_factory, db_engine):
        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": BUYER,
                "amount": 10_000,
                "value": 10_000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "LIQUIDITY_DEPOSIT",
                "chain_id": CHAIN,
                "payload": {"pool_id": "main", "lock_days": 0},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])

    def _setup_pool(self, session_factory, *, locked_until: datetime | None = None) -> None:
        from decimal import Decimal

        from aitbc_chain.state.liquidity import pool_main_address, pool_treasury_address

        _fund(session_factory, BUYER, pool_main_address(), pool_treasury_address())
        with session_factory() as session:
            session.add(
                LiquidityPool(
                    pool_id="main",
                    chain_id=CHAIN,
                    total_staked=10_000,
                    reward_per_share=Decimal("0.5"),
                )
            )
            session.add(
                LiquidityStake(
                    stake_id="lstake-1",
                    chain_id=CHAIN,
                    pool_id="main",
                    address=BUYER,
                    amount=10_000,
                    lock_days=0,
                    locked_until=locked_until,
                    reward_per_share_at_stake=Decimal("0"),
                    rewards_claimed=0,
                    status="active",
                )
            )
            session.commit()

    def test_liquidity_claim(self, session_factory, db_engine):
        self._setup_pool(session_factory)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": BUYER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "LIQUIDITY_CLAIM",
                "chain_id": CHAIN,
                "payload": {"pool_id": "main", "stake_id": "lstake-1"},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])

    def test_liquidity_withdraw(self, session_factory, db_engine):
        self._setup_pool(session_factory, locked_until=datetime(2020, 1, 1, tzinfo=UTC))
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": BUYER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "LIQUIDITY_WITHDRAW",
                "chain_id": CHAIN,
                "payload": {"pool_id": "main", "stake_id": "lstake-1"},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])


class TestStakeFamily:
    """Protocol transfers: keyless escrow senders carry no top-level
    signature; the journal sees the generic account writes + tx row."""

    def test_stake_lock(self, session_factory, db_engine):
        from aitbc_chain.protocol_escrow import stake_escrow_address

        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": stake_escrow_address(),
                "amount": 4000,
                "value": 4000,
                "fee": 0,
                "nonce": 0,
                "type": "STAKE_LOCK",
                "chain_id": CHAIN,
                "payload": {"stake_id": "1", "lock_days": 30},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])

    def test_stake_release(self, session_factory, db_engine):
        from aitbc_chain.protocol_escrow import stake_escrow_address

        escrow = stake_escrow_address()
        _fund(session_factory, escrow, balance=1_000_000)
        # Matured confirmed lock: block_height 1 + lock_days 1 * 1440 = 1441;
        # the apply block sits at 2000 so next_height (2000) >= 1441.
        lock_hash = _hash("stake-lock", "s1")
        with session_factory() as session:
            _mk_block_row(session, 1, "0x00", 1)
            session.add(
                ChainTransaction(
                    chain_id=CHAIN,
                    tx_hash=lock_hash,
                    block_height=1,
                    sender=BUYER,
                    recipient=escrow,
                    payload={"stake_id": "9", "lock_days": 1},
                    type="STAKE_LOCK",
                    value=4000,
                    fee=0,
                    nonce=0,
                    status="confirmed",
                )
            )
            session.commit()
        anc = _seeded_ancestor(session_factory, height=1999)
        release = {
            "from": escrow,
            "to": BUYER,
            "amount": 4000,
            "value": 4000,
            "fee": 0,
            "nonce": 0,
            "type": "STAKE_RELEASE",
            "chain_id": CHAIN,
            "payload": {"stake_id": "9", "lock_tx_hashes": [lock_hash]},
        }
        _roundtrip(session_factory, db_engine, 2000, anc["hash"], 1999, [release])


class TestBountyFamily:
    def test_bounty_lock(self, session_factory, db_engine):
        from aitbc_chain.protocol_escrow import bounty_escrow_address

        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        tx = _make_tx(
            BUYER_KEY,
            {
                "to": bounty_escrow_address(),
                "amount": 6000,
                "value": 6000,
                "fee": 0,
                "nonce": 0,
                "type": "BOUNTY_LOCK",
                "chain_id": CHAIN,
                "payload": {"bounty_id": "b-1"},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx])

    def _setup_bounty_escrow(self, session_factory) -> dict[str, Any]:
        from aitbc_chain.protocol_escrow import bounty_escrow_address

        _fund(session_factory, bounty_escrow_address(), balance=1_000_000)
        return _seeded_ancestor(session_factory)

    def test_bounty_payout(self, session_factory, db_engine):
        from aitbc_chain.protocol_escrow import bounty_escrow_address

        anc = self._setup_bounty_escrow(session_factory)
        payout = {
            "from": bounty_escrow_address(),
            "to": PROVIDER,
            "amount": 6000,
            "value": 6000,
            "fee": 0,
            "nonce": 0,
            "type": "BOUNTY_PAYOUT",
            "chain_id": CHAIN,
            "payload": {"bounty_id": "b-1", "submission_id": "sub-1"},
        }
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [payout])

    def test_bounty_refund(self, session_factory, db_engine):
        from aitbc_chain.protocol_escrow import bounty_escrow_address

        anc = self._setup_bounty_escrow(session_factory)
        refund = {
            "from": bounty_escrow_address(),
            "to": BUYER,
            "amount": 6000,
            "value": 6000,
            "fee": 0,
            "nonce": 0,
            "type": "BOUNTY_REFUND",
            "chain_id": CHAIN,
            "payload": {"bounty_id": "b-1"},
        }
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [refund])


class TestCompositeBlock:
    """Interaction effects inside ONE block — where capture merge/dedupe
    bugs hide (a single family per block can never produce them)."""

    def test_two_transfers_same_sender(self, session_factory, db_engine):
        """The same account row is raw-updated twice by one block — the
        before-image must keep the pre-block balance, not the mid one."""
        _fund(session_factory, BUYER)
        anc = _seeded_ancestor(session_factory)
        tx0 = _make_tx(
            BUYER_KEY,
            {
                "to": PROVIDER,
                "amount": 3000,
                "value": 3000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "TRANSFER",
                "chain_id": CHAIN,
            },
        )
        tx1 = _make_tx(
            BUYER_KEY,
            {
                "to": MARKET_A,
                "amount": 2000,
                "value": 2000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 1,
                "type": "TRANSFER",
                "chain_id": CHAIN,
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [tx0, tx1])

    def test_create_and_spend_new_account_same_block(self, session_factory, db_engine):
        """An account born inside the block then debited: undo is ins-undo +
        upd(before=None) — the row must not survive at all."""
        _fund(session_factory, BUYER, balance=2_000_000)
        anc = _seeded_ancestor(session_factory)
        fund = _make_tx(
            BUYER_KEY,
            {
                "to": NODE_WALLET,
                "amount": 800_000,
                "value": 800_000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "TRANSFER",
                "chain_id": CHAIN,
            },
        )
        spend = _make_tx(
            "0x" + "66" * 32,  # NODE_WALLET's key — the just-created account spends
            {
                "to": PROVIDER,
                "amount": 1000,
                "value": 1000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "TRANSFER",
                "chain_id": CHAIN,
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [fund, spend])

    def test_escrow_lock_and_release_same_block(self, session_factory, db_engine):
        """Escrow insert + update (release marks the lock) plus the four raw
        account writes — all inside one block."""
        _fund(session_factory, BUYER, NODE_WALLET, AUTH)
        _set_param(session_factory, "escrow_settlement_authority", AUTH)
        anc = _seeded_ancestor(session_factory)
        lock = _make_tx(
            BUYER_KEY,
            {
                "to": NODE_WALLET,
                "amount": 7000,
                "value": 7000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "ESCROW_LOCK",
                "chain_id": CHAIN,
                "payload": {"job_id": "job-combo-1", "provider": PROVIDER},
            },
        )
        release = _make_tx(
            AUTH_KEY,
            {
                "to": PROVIDER,
                "amount": 7000,
                "value": 7000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "ESCROW_RELEASE",
                "chain_id": CHAIN,
                "payload": {"job_id": "job-combo-1"},
            },
        )
        _roundtrip(session_factory, db_engine, 1, anc["hash"], 0, [lock, release])


class TestRequeueAdmissionPath:
    """The envelope's signed payload must pass the same admission gate a
    fresh submission faces — this is what makes the orphan-loss metric
    meaningful (a failure here is the only 'lost' path)."""

    def test_signed_envelope_survives_full_admission(self, session_factory, monkeypatch):
        from aitbc_chain.config import settings as chain_settings
        from aitbc_chain.rpc import transactions as rpc_tx
        from aitbc_chain.state.block_deltas import requeue_orphaned_transactions

        class ProbeMempool:
            def __init__(self):
                self.added: list[dict] = []

            def pending_cost(self, chain_id, sender, exclude_nonce=None):
                return 0

            def add(self, tx, chain_id=None, tx_hash=None, commit=True):
                self.added.append(tx)
                return tx_hash or "0x0"

        # The admission gate reads accounts through its own session_scope —
        # point it at the test DB and accept the test chain.
        monkeypatch.setattr(rpc_tx, "session_scope", session_factory)
        monkeypatch.setattr(chain_settings, "supported_chains", CHAIN)
        probe = ProbeMempool()
        monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: probe)
        _fund(session_factory, BUYER)

        envelope = _make_tx(
            BUYER_KEY,
            {
                "to": PROVIDER,
                "amount": 250,
                "value": 250,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "TRANSFER",
                "chain_id": CHAIN,
            },
        )
        envelope["tx_hash"] = _hash("orphan", 1)

        failed = requeue_orphaned_transactions(CHAIN, [envelope])
        assert failed == [] and len(probe.added) == 1
        assert probe.added[0]["signature"] == envelope["signature"]
