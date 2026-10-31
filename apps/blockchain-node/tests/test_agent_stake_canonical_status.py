"""#719 second half — canonical agent-stake status from sealed history.

``_canonical_status`` reads sealed STAKE_UNBOND/STAKE_RELEASE markers before
the node-local ``agent_stake`` row, so a host that never served the stake
answers from sealed txs instead of 404-blind, and a stale local row cannot
mask a sealed transition. Precedence: RELEASE > UNBOND > local row > LOCK.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc_chain.base_models import AgentStakeRecord, _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Transaction
from aitbc_chain.rpc.agent_staking import _canonical_status

CHAIN = "bc-2"
STAKER = _to_ait_address("0x" + "1" * 40)
ESCROW = _to_ait_address("0x" + "2" * 40)
SID = "stress-stake-test-1"


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


def _tx(tx_hash: str, tx_type: str, payload: dict) -> Transaction:
    return Transaction(
        chain_id=CHAIN,
        tx_hash=tx_hash,
        block_height=100,
        sender=ESCROW,
        recipient=ESCROW,
        payload=payload,
        type=tx_type,
        status="confirmed",
        timestamp="2026-10-31T12:00:00+00:00",
    )


def _sealed(session: Session, tx_type: str, n: int = 1) -> None:
    for i in range(n):
        session.add(_tx(f"0x{i:064x}", tx_type, {"agent_stake_id": SID}))
    session.commit()


def _row(session: Session, status: str = "active") -> None:
    session.add(
        AgentStakeRecord(
            chain_id=CHAIN,
            stake_id=SID,
            staker_address=STAKER,
            agent_wallet=STAKER,
            amount=1000,
            locked_until=datetime.now(UTC) - timedelta(hours=1),
            status=status,
        )
    )
    session.commit()


def test_no_local_row_sealed_unbond_reads_unbonding_from_chain(engine):
    """Host-B: no agent_stake row, sealed STAKE_UNBOND → unbonding/chain."""
    with Session(engine) as session:
        _sealed(session, "STAKE_UNBOND")
        assert _canonical_status(session, CHAIN, SID) == ("unbonding", "chain")


def test_local_unbonding_sealed_release_reads_completed(engine):
    """Stale local 'unbonding' + sealed STAKE_RELEASE → completed/chain."""
    with Session(engine) as session:
        _row(session, "unbonding")
        _sealed(session, "STAKE_RELEASE")
        assert _canonical_status(session, CHAIN, SID) == ("completed", "chain")


def test_local_row_fallback_no_markers(engine):
    with Session(engine) as session:
        _row(session, "active")
        assert _canonical_status(session, CHAIN, SID) == ("active", "local")


def test_no_row_only_lock_reads_active_from_chain(engine):
    with Session(engine) as session:
        _sealed(session, "STAKE_LOCK")
        assert _canonical_status(session, CHAIN, SID) == ("active", "chain")


def test_nothing_anywhere_reads_none(engine):
    with Session(engine) as session:
        assert _canonical_status(session, CHAIN, SID) == (None, "none")


def test_unsealed_txs_dont_count(engine):
    """block_height=None (still mempool) must not beat the local row."""
    with Session(engine) as session:
        _row(session, "active")
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0x" + "9" * 64,
                block_height=None,
                sender=ESCROW,
                recipient=ESCROW,
                payload={"agent_stake_id": SID},
                type="STAKE_UNBOND",
                status="pending",
                timestamp="2026-10-31T12:00:00+00:00",
            )
        )
        session.commit()
        assert _canonical_status(session, CHAIN, SID) == ("active", "local")
