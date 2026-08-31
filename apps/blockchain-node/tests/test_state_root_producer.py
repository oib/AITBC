"""Regression test for the producer-side stale-state-root bug.

The producer in ``aitbc_chain.consensus.poa`` applies transactions with raw
SQL ``UPDATE`` statements (see ``state_transition.apply_transaction``) and then
computes the block header ``state_root`` with ``compute_state_root_full``.

An earlier version of ``compute_state_root_full`` used an ORM ``select(Account)``
query. Because the raw SQL updates do not refresh the SQLAlchemy identity map,
that ORM query returned the in-memory ``Account`` objects with their stale
pre-transaction balances. The producer then wrote a block whose ``state_root``
corresponded to the *parent* block's state, exactly the symptom observed in
block 1486 (the block 1486 header carried block 1484's state root).

This test verifies that the current implementation reads the database row state
directly, even when the same ``Session`` already has ``Account`` objects loaded,
and that an empty follow-up block inherits the post-transaction state root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select, text

from aitbc_chain.base_models import Account
from aitbc_chain.database import chain_metadata
from aitbc_chain.models import Block
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition


@pytest.fixture
def engine():
    """In-memory SQLite engine with a fresh schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    return engine


def _make_transfer_tx(
    from_addr: str,
    to_addr: str,
    value: int,
    fee: int,
    nonce: int,
) -> dict:
    return {
        "from": from_addr,
        "to": to_addr,
        "value": value,
        "fee": fee,
        "nonce": nonce,
        "chain_id": "ait-test",
        "type": "TRANSFER",
        "signature": "0x" + "aa" * 65,
    }


def test_state_root_full_sees_raw_sql_updates(engine):
    """compute_state_root_full must reflect raw SQL balance changes in the same transaction."""
    chain_id = "ait-test"
    sender = "0x1d8B34f249b96169E48E956b00c307898FbaF087"
    recipient = "0x17B9ED0c216932F6457c491808FF4d28bcbb679d"
    value = 5_000
    fee = 1_000

    # Initial state: sender has funds, recipient is empty.
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=sender, balance=1_000_000, nonce=0))
        session.add(Account(chain_id=chain_id, address=recipient, balance=0, nonce=0))
        session.commit()

    # Simulate what the producer does:
    #   1. Open a session.
    #   2. (The session may already have Account objects loaded, e.g. from a
    #      batch pre-fetch in the proposer loop or from the previous block.)
    #   3. Apply the transfer with state_transition, which uses raw SQL UPDATE.
    #   4. Compute the state root with compute_state_root_full.
    with Session(engine) as session:
        pre_root = compute_state_root_full(session, chain_id)

        # Force the stale-identity-map scenario by loading the Account ORM
        # objects before the raw SQL update runs.
        for row in session.execute(
            text("SELECT address, balance, nonce FROM account WHERE chain_id = :chain_id"),
            {"chain_id": chain_id},
        ).all():
            session.get(Account, (chain_id, row[0]))

        tx = _make_transfer_tx(sender, recipient, value, fee, nonce=0)
        with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
            ok, msg = StateTransition().apply_transaction(session, chain_id, tx, "0x" + "ab" * 32)
        assert ok, msg

        post_root = compute_state_root_full(session, chain_id)
        # The producer commits the block and the updated account state together.
        session.commit()

    assert pre_root is not None
    assert post_root is not None
    assert post_root != pre_root, "state root must change after a transfer"

    # After the producer commits block N, a later block N+1 with no new
    # transactions must use the same post-transaction state root.
    with Session(engine) as session:
        block_n = Block(
            chain_id=chain_id,
            height=0,
            hash="0x" + "00" * 32,
            parent_hash="0x" + "00" * 32,
            proposer="proposer-a",
            timestamp=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
            tx_count=1,
            state_root=post_root,
        )
        session.add(block_n)
        session.commit()

    # Now the follow-up block producer opens a fresh session and recomputes.
    with Session(engine) as session:
        next_root = compute_state_root_full(session, chain_id)
        block_n1 = Block(
            chain_id=chain_id,
            height=1,
            hash="0x" + "11" * 32,
            parent_hash="0x" + "00" * 32,
            proposer="proposer-a",
            timestamp=datetime(2026, 8, 31, 12, 0, 1, tzinfo=UTC),
            tx_count=0,
            state_root=next_root,
        )
        session.add(block_n1)
        session.commit()

    # Both blocks should share the post-transfer state root; block N+1 must not
    # revert to the pre-transfer (parent-of-N) root.
    with Session(engine) as session:
        stored_n = session.exec(select(Block).where(Block.chain_id == chain_id, Block.height == 0)).first()
        stored_n1 = session.exec(select(Block).where(Block.chain_id == chain_id, Block.height == 1)).first()
        assert stored_n is not None
        assert stored_n1 is not None
        assert stored_n1.state_root == stored_n.state_root, "empty block N+1 must carry the same state root as block N"
        assert stored_n1.state_root == post_root, "empty block N+1 must use the post-transaction state root"
        assert stored_n1.state_root != pre_root, "empty block N+1 must not revert to the pre-transaction (parent) state root"
