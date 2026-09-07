"""
S-4: Per-escrow addresses — locked funds go to deterministic escrow:<job_id>
addresses instead of the node wallet's spendable balance.

For block_version >= 3:
- ESCROW_LOCK credits the escrow address (no known key → unspendable)
- ESCROW_RELEASE/ESCROW_REFUND debits the escrow address
- The node wallet's balance never includes escrowed funds
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import (
    StateTransition,
    _escrow_address,
)


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test_s4.db"
    engine = create_engine(f"sqlite:///{db_path}")
    chain_metadata.create_all(engine)
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO account (chain_id, address, balance, nonce, updated_at) "
                "VALUES (:chain_id, :addr, :balance, 0, :now)"
            ),
            {"chain_id": "test", "addr": "buyer1", "balance": 10000, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO account (chain_id, address, balance, nonce, updated_at) "
                "VALUES (:chain_id, :addr, :balance, 0, :now)"
            ),
            {"chain_id": "test", "addr": "node_wallet", "balance": 0, "now": now},
        )
        session.commit()
    yield engine
    engine.dispose()


def _make_escrow_lock(job_id: str, buyer: str, node: str, amount: int) -> dict:
    return {
        "from": buyer,
        "to": node,
        "value": amount,
        "fee": 0,
        "type": "ESCROW_LOCK",
        "payload": {"job_id": job_id, "provider": "provider1"},
        "nonce": 0,
    }


def _make_escrow_release(job_id: str, node: str, provider: str, amount: int) -> dict:
    return {
        "from": node,
        "to": provider,
        "value": amount,
        "fee": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": job_id, "action": "escrow_release"},
        "nonce": 0,
    }


def test_escrow_address_is_deterministic():
    """The same job_id always produces the same escrow address."""
    addr1 = _escrow_address("job-123")
    addr2 = _escrow_address("job-123")
    addr3 = _escrow_address("job-456")
    assert addr1 == addr2
    assert addr1 != addr3
    assert addr1.startswith("0x")


def test_v3_escrow_lock_credits_escrow_address_not_node(engine):
    """For block_version >= 3, ESCROW_LOCK credits the escrow address, not the node."""
    st = StateTransition()
    job_id = "job-s4-lock"
    escrow_addr = _escrow_address(job_id)
    tx = _make_escrow_lock(job_id, "buyer1", "node_wallet", 500)

    with Session(engine) as session:
        result = st.apply_transaction(session, "test", tx, "tx-s4-lock-1", block_version=3)
        session.commit()
        assert result[0] is True

        # Check balances
        buyer_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='buyer1'")
        ).scalar()
        node_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='node_wallet'")
        ).scalar()
        escrow_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address=:addr"),
            {"addr": escrow_addr},
        ).scalar()

    assert buyer_balance == 9500  # 10000 - 500
    assert node_balance == 0  # node wallet didn't receive the funds
    assert escrow_balance == 500  # escrow address holds the locked funds


def test_v2_escrow_lock_credits_node_wallet(engine):
    """For block_version 2, ESCROW_LOCK still credits the node wallet (backward compat)."""
    st = StateTransition()
    job_id = "job-s4-v2"
    tx = _make_escrow_lock(job_id, "buyer1", "node_wallet", 300)

    with Session(engine) as session:
        result = st.apply_transaction(session, "test", tx, "tx-s4-v2-1", block_version=2)
        session.commit()
        assert result[0] is True

        node_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='node_wallet'")
        ).scalar()

    assert node_balance == 300  # v2: node wallet receives the funds


def test_v3_escrow_release_moves_from_escrow_address(engine):
    """For block_version >= 3, ESCROW_RELEASE moves funds from the escrow address."""
    st = StateTransition()
    job_id = "job-s4-release"
    escrow_addr = _escrow_address(job_id)

    with Session(engine) as session:
        # First lock funds
        lock_tx = _make_escrow_lock(job_id, "buyer1", "node_wallet", 500)
        st.apply_transaction(session, "test", lock_tx, "tx-s4-rel-lock", block_version=3)
        session.commit()

        # Now release to provider
        release_tx = _make_escrow_release(job_id, "node_wallet", "provider1", 500)
        result = st.apply_transaction(session, "test", release_tx, "tx-s4-rel-1", block_version=3)
        session.commit()
        assert result[0] is True

        escrow_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address=:addr"),
            {"addr": escrow_addr},
        ).scalar()
        provider_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='provider1'")
        ).scalar()
        node_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='node_wallet'")
        ).scalar()

    assert escrow_balance == 0  # funds left the escrow
    assert provider_balance == 500  # provider received them
    assert node_balance == 0  # node wallet was never touched
