"""Consensus tests: v4 stake lock windows (GAP-42 remainder).

Pre-v4, a STAKE_RELEASE was an ordinary escrow→user transfer whose only guard
was the HTTP route's check against a node-local ``stake`` row — invisible to
consensus and absent on followers. From ``state_transition_v4_height`` a
release must name its lock transactions (``payload.lock_tx_hashes``), every
lock must belong to the payee and have matured (``lock_days`` × 1440 blocks at
the fixed 60s cadence), the claimed set must not overlap a sealed release, and
the summed principal must cover the release value. Locks with no ``lock_days``
(legacy block-7306, agent stakes, auto-stake top-ups) are treated as matured.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine, text
from sqlmodel import Session

from aitbc_chain.base_models import Block, _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Transaction
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "test"
STAKER_KEY = keys.PrivateKey(b"\x11" * 32)
STAKER = STAKER_KEY.public_key.to_checksum_address()
OTHER = keys.PrivateKey(b"\x22" * 32).public_key.to_checksum_address()
ESCROW = "0x00000000000000000000000000000000000e5c09"
HEAD = 5000  # sealed parent height — releases land in HEAD+1


def _sign(message: dict[str, Any], key: keys.PrivateKey = STAKER_KEY) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _auth(message: dict[str, Any]) -> dict[str, Any]:
    return {"signer": STAKER, "message": message, "signature": _sign(message)}


def _release(payload: dict[str, Any], *, value: int = 1000, recipient: str = STAKER) -> dict[str, Any]:
    return {
        "from": ESCROW,
        "to": recipient,
        "amount": value,
        "value": value,
        "fee": 0,
        "nonce": 0,
        "type": "STAKE_RELEASE",
        "payload": payload,
        "chain_id": CHAIN,
    }


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(engine)
    now = datetime.now(UTC).isoformat()
    with Session(engine) as session:
        for addr, balance in ((STAKER, 10**9), (ESCROW, 10**9), (OTHER, 10**6)):
            session.execute(
                text(
                    "INSERT INTO account (chain_id, address, balance, nonce, updated_at) "
                    "VALUES (:chain_id, :addr, :balance, 0, :now)"
                ),
                {"chain_id": CHAIN, "addr": _to_ait_address(addr), "balance": balance, "now": now},
            )
        for h in range(HEAD - 100, HEAD + 1):
            session.add(
                Block(
                    chain_id=CHAIN,
                    height=h,
                    hash=f"0x{h:064x}",
                    parent_hash=f"0x{h - 1:064x}",
                    proposer="0x" + "0" * 40,
                )
            )
        session.commit()
    yield engine
    engine.dispose()


def _add_lock(
    session: Session,
    tx_hash: str,
    *,
    sender: str = STAKER,
    value: int = 1000,
    height: int = HEAD - 50,
    lock_days: Any = "absent",
) -> None:
    payload: dict[str, Any] = {"stake_id": "s1"}
    if lock_days != "absent":
        payload["lock_days"] = lock_days
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            block_height=height,
            sender=sender,
            recipient=ESCROW,
            payload=payload,
            value=value,
            fee=0,
            nonce=0,
            type="STAKE_LOCK",
            status="confirmed",
        )
    )


def _validate(engine, tx, *, block_version: int) -> tuple[bool, str]:
    with Session(engine) as session:
        return StateTransition().validate_transaction(
            session, CHAIN, tx, tx.get("_hash", "0xrel1"), block_version=block_version
        )


def test_v4_release_without_lock_hashes_rejected(engine):
    tx = _release({"stake_id": "s1"})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "lock_tx_hashes" in msg


def test_v3_release_without_lock_hashes_still_accepted(engine):
    """Pre-v4 sealed releases carry no lock_tx_hashes — they must replay."""
    tx = _release({"stake_id": "s1"})
    ok, msg = _validate(engine, tx, block_version=3)
    assert ok is True, msg


def test_v4_unknown_lock_rejected(engine):
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xnonexistent"]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "unknown or unconfirmed" in msg


def test_v4_lock_belonging_to_other_rejected(engine):
    with Session(engine) as session:
        _add_lock(session, "0xlock1", sender=OTHER)
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "not payee" in msg


def test_v4_release_exceeding_principal_rejected(engine):
    with Session(engine) as session:
        _add_lock(session, "0xlock1", value=1000)
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]}, value=2000)
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "exceeds locked principal" in msg


def test_v4_immature_lock_rejected(engine):
    """lock_days=30 at height HEAD-50 → unlock at HEAD-50+43200; far future."""
    with Session(engine) as session:
        _add_lock(session, "0xlock1", height=HEAD - 50, lock_days=30)
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "matures at height" in msg


def test_v4_matured_lock_accepted(engine):
    """lock_days=2 sealed ~3 days of blocks ago → matured."""
    with Session(engine) as session:
        _add_lock(session, "0xlock1", height=HEAD - 3 * 1440, lock_days=2)
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is True, msg


def test_v4_legacy_lock_without_days_accepted(engine):
    """The block-7306 lock carries no lock_days — treated as matured."""
    with Session(engine) as session:
        _add_lock(session, "0xlock7306", height=7306)
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock7306"]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is True, msg


def test_v4_lock_days_zero_accepted(engine):
    """Agent/auto-stake locks declare lock_days=0 — no consensus window."""
    with Session(engine) as session:
        _add_lock(session, "0xlock1", lock_days=0)
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is True, msg


def test_v4_already_released_lock_rejected(engine):
    with Session(engine) as session:
        _add_lock(session, "0xlock1")
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0xprior-rel",
                block_height=HEAD - 10,
                sender=ESCROW,
                recipient=STAKER,
                payload={"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]},
                value=1000,
                fee=0,
                nonce=0,
                type="STAKE_RELEASE",
                status="confirmed",
            )
        )
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "already released" in msg


def test_v4_multi_lock_release_accepted(engine):
    """Agent stakes aggregate top-up locks — the set sums the principal."""
    with Session(engine) as session:
        _add_lock(session, "0xlock1", value=700)
        _add_lock(session, "0xlock2", value=300)
        session.commit()
    tx = _release({"agent_stake_id": "a1", "lock_tx_hashes": ["0xlock1", "0xlock2"]}, value=1000)
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is True, msg


def test_v4_duplicate_hash_in_claim_rejected(engine):
    with Session(engine) as session:
        _add_lock(session, "0xlock1")
        session.commit()
    tx = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1", "0xLOCK1".lower()]})
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "duplicates" in msg


def test_auth_message_naming_different_locks_rejected(engine):
    """When the signed message does name lock_tx_hashes, it must match."""
    with Session(engine) as session:
        _add_lock(session, "0xlock1")
        session.commit()
    message = {
        "address": STAKER,
        "stake_id": "s1",
        "chain_id": CHAIN,
        "action": "unstake",
        "lock_tx_hashes": ["0xother"],
    }
    tx = _release(
        {"stake_id": "s1", "lock_tx_hashes": ["0xlock1"], "auth": _auth(message)},
    )
    ok, msg = _validate(engine, tx, block_version=4)
    assert ok is False
    assert "auth" in msg.lower()


def test_mempool_rejects_second_pending_release_for_same_lock(engine, tmp_path):
    """Two pending releases may claim one lock — only confirmed history is
    consensus state, so the mempool dedups them before the proposer drains."""
    from aitbc_chain.mempool import DatabaseMempool, InMemoryMempool

    for mempool in (
        InMemoryMempool(min_fee=0),
        DatabaseMempool(f"sqlite:///{tmp_path / 'mp.db'}", min_fee=0),
    ):
        first = _release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]})
        second = _release({"stake_id": "s2", "lock_tx_hashes": ["0xlock1", "0xlock9"]})
        mempool.add(first, chain_id=CHAIN)
        with pytest.raises(ValueError, match="pending release"):
            mempool.add(second, chain_id=CHAIN)


def test_mempool_allows_release_with_distinct_locks(engine):
    from aitbc_chain.mempool import InMemoryMempool

    mempool = InMemoryMempool(min_fee=0)
    mempool.add(_release({"stake_id": "s1", "lock_tx_hashes": ["0xlock1"]}), chain_id=CHAIN)
    h = mempool.add(_release({"stake_id": "s2", "lock_tx_hashes": ["0xlock2"]}), chain_id=CHAIN)
    assert h
