"""
Regression tests for EscrowManager DB loading and refund route idempotency.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from aitbc_chain.base_models import Escrow
from aitbc_chain.contracts.escrow import EscrowManager, EscrowState, create_escrow_manager
from aitbc_chain.rpc.escrow_routes import refund_escrow


# The escrow foreign keys are chain-scoped, so every record has to name its chain. This is
# the id the `escrow_engine` fixture installs as the default.
CHAIN_ID = "test"

# Valid AIT-style addresses (ait1 + 40 hex chars)
BUYER = "ait1" + "0" * 40
PROVIDER = "ait1" + "1" * 40


@pytest.fixture
def escrow_engine(monkeypatch, engine):
    """Route EscrowManager DB access to the test in-memory engine."""
    from aitbc_chain import database

    monkeypatch.setattr(database, "_default_chain_id", CHAIN_ID)
    monkeypatch.setattr(database, "_engines", {"test": engine})
    monkeypatch.setattr(database, "_session_factories", {})
    return engine


@pytest.fixture
def manager(escrow_engine) -> EscrowManager:
    """Create and install a fresh EscrowManager with the test engine."""
    from aitbc_chain.contracts import escrow

    original = escrow.escrow_manager
    mgr = create_escrow_manager()
    yield mgr
    escrow.escrow_manager = original


def _insert_escrow(session, job_id: str, released_at=None, refunded_at=None, refund_tx_hash=None):
    record = Escrow(
        job_id=job_id,
        chain_id=CHAIN_ID,
        buyer=BUYER,
        provider=PROVIDER,
        amount=5,
        created_at=datetime.now(UTC),
        released_at=released_at,
        refunded_at=refunded_at,
        refund_tx_hash=refund_tx_hash,
    )
    session.add(record)
    session.commit()
    return record


@pytest.mark.unit
class TestEscrowManagerPersistence:
    """EscrowManager loads and lazy-loads persisted escrow records."""

    def test_load_from_db_loads_only_active_escrows(self, manager, session):
        """load_from_db loads active escrows and skips released/refunded ones."""
        _insert_escrow(session, "job-active-1")
        _insert_escrow(session, "job-released-1", released_at=datetime.now(UTC))
        _insert_escrow(session, "job-refunded-1", refunded_at=datetime.now(UTC))

        asyncio.run(manager.load_from_db())

        assert len(manager.escrow_contracts) == 1
        contract = list(manager.escrow_contracts.values())[0]
        assert contract.job_id == "job-active-1"
        assert contract.state == EscrowState.FUNDED
        assert contract.contract_id in manager.active_contracts

    def test_get_or_load_contract_returns_refunded_state(self, manager, session):
        """Lazy loading an already-refunded record returns a REFUNDED contract."""
        _insert_escrow(session, "job-refunded-2", refunded_at=datetime.now(UTC), refund_tx_hash="0xdeadbeef")

        contract = asyncio.run(manager.get_or_load_contract("job-refunded-2"))

        assert contract is not None
        assert contract.state == EscrowState.REFUNDED
        assert contract.refunded_amount == Decimal(5)
        expected_id = "escrow_" + hashlib.sha256(f"{BUYER}:{PROVIDER}:job-refunded-2".encode()).hexdigest()[:16]
        assert contract.contract_id == expected_id

        # Second load must return the same in-memory object.
        contract2 = asyncio.run(manager.get_or_load_contract("job-refunded-2"))
        assert contract2 is contract

    def test_get_or_load_contract_uses_ait_amount_not_compute_seconds(self, manager, session):
        """Loaded contract amount is in AIT (DB amount), not divided by 3600."""
        _insert_escrow(session, "job-active-2")

        contract = asyncio.run(manager.get_or_load_contract("job-active-2"))

        assert contract is not None
        assert contract.amount == Decimal(5)


@pytest.mark.unit
class TestEscrowRefundRoute:
    """The /escrow/{job_id}/refund route is idempotent and updates the DB."""

    def test_refund_escrow_is_idempotent(self, manager, session):
        """Calling refund on an already-refunded contract returns the stored tx hash."""
        _insert_escrow(
            session,
            "job-route-refund-1",
            refunded_at=datetime.now(UTC),
            refund_tx_hash="0xalreadythere",
        )

        # Pre-load the refunded contract into the manager.
        asyncio.run(manager.get_or_load_contract("job-route-refund-1"))

        result = asyncio.run(refund_escrow("job-route-refund-1", {}))

        assert result["success"] is True
        assert result["refund_tx_hash"] == "0xalreadythere"
        assert result["message"] == "Escrow already refunded"

    def test_refund_escrow_updates_db_for_active_contract(self, manager, session):
        """Refunding an active escrow updates the record with refunded_at and refund_tx_hash."""
        _insert_escrow(session, "job-route-refund-2")

        result = asyncio.run(refund_escrow("job-route-refund-2", {}))

        assert result["success"] is True
        assert result["refund_tx_hash"].startswith("0x")
        assert result["job_id"] == "job-route-refund-2"

        record = session.get(Escrow, "job-route-refund-2")
        assert record.refunded_at is not None
        assert record.refund_tx_hash == result["refund_tx_hash"]

        contract = manager.escrow_contracts[result["contract_id"]]
        assert contract.state == EscrowState.REFUNDED
