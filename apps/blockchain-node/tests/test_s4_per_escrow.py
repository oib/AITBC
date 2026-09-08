"""
S-4: Per-escrow addresses — locked funds go to deterministic escrow:<job_id>
addresses instead of the node wallet's spendable balance.

For block_version >= 3:
- ESCROW_LOCK credits the escrow address (no known key → unspendable)
- ESCROW_RELEASE/ESCROW_REFUND debits the escrow address
- The node wallet's balance never includes escrowed funds
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session

from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.base_models import Block, Transaction
from aitbc_chain.state.state_transition import (
    StateTransition,
    _escrow_address,
    get_block_version,
    get_block_version_for_height,
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


def _make_escrow_refund(job_id: str, node: str, buyer: str, amount: int) -> dict:
    return {
        "from": node,
        "to": buyer,
        "value": amount,
        "fee": 0,
        "type": "ESCROW_REFUND",
        "payload": {"job_id": job_id, "action": "escrow_refund"},
        "nonce": 0,
    }


def _record_lock(session, chain_id: str, tx_data: dict, tx_hash: str, block_version: int) -> None:
    """Persist the lock transaction so release/refund validation can find it."""
    session.add(
        Transaction(
            chain_id=chain_id,
            tx_hash=tx_hash,
            block_height=None,
            sender=tx_data["from"],
            recipient=tx_data["to"],
            payload=tx_data.get("payload") or {},
            value=tx_data.get("value", 0),
            fee=tx_data.get("fee", 0),
            nonce=tx_data.get("nonce", 0),
            type="ESCROW_LOCK",
            status="confirmed",
            timestamp=datetime.now(UTC).isoformat(),
        )
    )


def _record_block(session, chain_id: str, height: int, version: int) -> None:
    """Create a minimal block record with the given state transition version."""
    from aitbc_chain.base_models import Block

    metadata = {"state_transition_version": version} if version else {}
    session.add(
        Block(
            chain_id=chain_id,
            height=height,
            hash=f"hash-{height}",
            parent_hash=f"hash-{height - 1}" if height else "genesis",
            timestamp=datetime.now(UTC),
            state_root="0x" + "0" * 64,
            proposer="proposer",
            tx_count=0,
            block_metadata=json.dumps(metadata) if metadata else "",
        )
    )


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
        _record_lock(session, "test", tx, "tx-s4-lock-1", 3)
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
        _record_lock(session, "test", tx, "tx-s4-v2-1", 2)
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
        _record_lock(session, "test", lock_tx, "tx-s4-rel-lock", 3)
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


def test_v3_escrow_refund_moves_from_escrow_address(engine):
    """For block_version >= 3, ESCROW_REFUND returns funds to the buyer."""
    st = StateTransition()
    job_id = "job-s4-refund"
    escrow_addr = _escrow_address(job_id)

    with Session(engine) as session:
        lock_tx = _make_escrow_lock(job_id, "buyer1", "node_wallet", 500)
        st.apply_transaction(session, "test", lock_tx, "tx-s4-ref-lock", block_version=3)
        _record_lock(session, "test", lock_tx, "tx-s4-ref-lock", 3)
        session.commit()

        refund_tx = _make_escrow_refund(job_id, "node_wallet", "buyer1", 500)
        result = st.apply_transaction(session, "test", refund_tx, "tx-s4-ref-1", block_version=3)
        session.commit()
        assert result[0] is True

        escrow_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address=:addr"),
            {"addr": escrow_addr},
        ).scalar()
        buyer_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='buyer1'")
        ).scalar()
        node_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='node_wallet'")
        ).scalar()

    assert escrow_balance == 0
    assert buyer_balance == 10000  # refunded in full
    assert node_balance == 0


def test_v3_release_rejects_wrong_beneficiary(engine):
    """A v3 ESCROW_RELEASE must pay the provider recorded in the lock."""
    st = StateTransition()
    job_id = "job-s4-wrong-beneficiary"

    with Session(engine) as session:
        lock_tx = _make_escrow_lock(job_id, "buyer1", "node_wallet", 500)
        st.apply_transaction(session, "test", lock_tx, "tx-s4-wb-lock", block_version=3)
        _record_lock(session, "test", lock_tx, "tx-s4-wb-lock", 3)
        session.commit()

        release_tx = _make_escrow_release(job_id, "node_wallet", "attacker", 500)
        result = st.apply_transaction(session, "test", release_tx, "tx-s4-wb-rel", block_version=3)
        session.commit()
        assert result[0] is False
        assert "provider1" in result[1]


def test_v3_release_enforces_settlement_authority(engine):
    """A v3 ESCROW_RELEASE must be signed by the configured settlement authority."""
    st = StateTransition()
    job_id = "job-s4-authority"

    with Session(engine) as session:
        lock_tx = _make_escrow_lock(job_id, "buyer1", "node_wallet", 500)
        st.apply_transaction(session, "test", lock_tx, "tx-s4-auth-lock", block_version=3)
        _record_lock(session, "test", lock_tx, "tx-s4-auth-lock", 3)
        session.commit()

        previous_authority = settings.escrow_settlement_authority
        settings.escrow_settlement_authority = "0xallowedsettlementauthority"
        try:
            release_tx = _make_escrow_release(job_id, "node_wallet", "provider1", 500)
            result = st.apply_transaction(session, "test", release_tx, "tx-s4-auth-rel", block_version=3)
            assert result[0] is False
            assert "settlement authority" in result[1]
        finally:
            settings.escrow_settlement_authority = previous_authority


def test_v2_lock_can_be_released_after_v3_activation(engine):
    """A v2 lock (funds in node wallet) can still be released in a v3 block."""
    st = StateTransition()
    job_id = "job-s4-cross-activation"
    v2_block_height = 100

    with Session(engine) as session:
        _record_block(session, "test", v2_block_height, 2)

        lock_tx = _make_escrow_lock(job_id, "buyer1", "node_wallet", 300)
        st.apply_transaction(session, "test", lock_tx, "tx-s4-ca-lock", block_version=2)
        session.add(
            Transaction(
                chain_id="test",
                tx_hash="tx-s4-ca-lock",
                block_height=v2_block_height,
                sender=lock_tx["from"],
                recipient=lock_tx["to"],
                payload=lock_tx.get("payload") or {},
                value=lock_tx.get("value", 0),
                fee=lock_tx.get("fee", 0),
                nonce=lock_tx.get("nonce", 0),
                type="ESCROW_LOCK",
                status="confirmed",
                timestamp=datetime.now(UTC).isoformat(),
            )
        )
        session.commit()

        release_tx = _make_escrow_release(job_id, "node_wallet", "provider1", 300)
        result = st.apply_transaction(session, "test", release_tx, "tx-s4-ca-rel", block_version=3)
        session.commit()
        assert result[0] is True

        provider_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='provider1'")
        ).scalar()
        node_balance = session.execute(
            text("SELECT balance FROM account WHERE chain_id='test' AND address='node_wallet'")
        ).scalar()

    assert provider_balance == 300
    assert node_balance == 0


def test_block_version_helper_defaults():
    """get_block_version_for_height follows activation thresholds and default-0 is safe."""
    assert get_block_version_for_height(0) == 1
    assert get_block_version_for_height(1000) == 1


def test_get_block_version_uses_metadata():
    """A block with explicit state_transition_version overrides the threshold fallback."""
    block = Block(
        chain_id="test",
        height=1,
        hash="0x" + "0" * 64,
        parent_hash="0x" + "1" * 64,
        timestamp=datetime.now(UTC),
        state_root="0x" + "2" * 64,
        proposer="p",
        tx_count=0,
        block_metadata=json.dumps({"state_transition_version": 3}),
    )
    assert get_block_version(block, 1) == 3
