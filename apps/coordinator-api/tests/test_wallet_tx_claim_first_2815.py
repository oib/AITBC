"""#2815: execute_wallet_transaction must claim the spend BEFORE the chain call.

Previously ``validate_consume`` was check-only, ``adapter.execute_transaction``
broadcast the signed tx, and ``apply_consume`` + ``wallet.total_spent`` +
``session.commit()`` ran last — a crash or commit failure after the send left
AIT moved on-chain with ``used_ait``/``total_spent`` never recorded, so the
session cap and wallet spending_limit under-counted permanently, and an
ambiguous-timeout retry could double-spend within cap.

These pins cover: claim committed before broadcast, definite pre-send
ValueError releasing the reservation, ambiguous failures keeping it, and cap
enforcement happening at claim time (adapter never called on cap breach).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.agent_identity.domain.agent_identity import (
    AgentIdentity,
    AgentSpendSession,
    AgentWallet,
    WalletAuditLog,
)
from coordinator_api.contexts.agent_identity.domain.spend_policy import (
    SpendSessionCapError,
    SpendSessionRequiredError,
)
from coordinator_api.contexts.agent_identity.services.manager import AgentWalletManager
from coordinator_api.contexts.agent_identity.services.spend_session_service import SpendSessionService

AGENT = "agent-claim-1"
OWNER = "0x" + "11" * 20
CHAIN_ID = 1000
TO = "0x" + "22" * 20
WALLET_ADDR = "0x" + "33" * 20


@pytest.fixture
def claim_session(db_session: Session) -> Session:
    db_session.add(AgentIdentity(agent_id=AGENT, owner_address=OWNER))
    db_session.add(
        AgentWallet(
            agent_id=AGENT,
            chain_id=CHAIN_ID,
            chain_address=WALLET_ADDR,
            is_active=True,
            permissions=["wallet.execute"],
            spending_limit=Decimal("0"),
        )
    )
    db_session.commit()
    return db_session


def _spend_session(db_session: Session, cap: str = "10") -> AgentSpendSession:
    svc = SpendSessionService(db_session)
    return svc.create_session(AGENT, OWNER, CHAIN_ID, Decimal(cap), ["wallet.execute"], None)


def _manager(db_session: Session, adapter) -> AgentWalletManager:
    manager = AgentWalletManager(db_session)
    manager._get_adapter = lambda chain_id: adapter
    return manager


def _wallet(db_session: Session) -> AgentWallet:
    return db_session.exec(select(AgentWallet).where(AgentWallet.agent_id == AGENT, AgentWallet.chain_id == CHAIN_ID)).one()


def _session_row(db_session: Session, session_id: str) -> AgentSpendSession:
    return db_session.get(AgentSpendSession, session_id)


def _events(db_session: Session) -> list[str]:
    return [r.event for r in db_session.exec(select(WalletAuditLog).where(WalletAuditLog.agent_id == AGENT)).all()]


def _data(session_id: str) -> dict:
    return {"session_id": session_id, "ref": "ref-1"}


@pytest.mark.asyncio
async def test_success_claims_before_send_and_confirms(claim_session):
    db = claim_session
    spend = _spend_session(db)
    adapter = AsyncMock()
    adapter.execute_transaction = AsyncMock(return_value={"transaction_hash": "0xtx1", "status": "pending"})
    manager = _manager(db, adapter)

    result = await manager.execute_wallet_transaction(AGENT, CHAIN_ID, TO, Decimal("2.5"), _data(spend.id))

    assert result["transaction_hash"] == "0xtx1"
    assert _session_row(db, spend.id).used_ait == Decimal("2.5")
    wallet = _wallet(db)
    assert wallet.total_spent == Decimal("2.5")
    assert wallet.transaction_count == 1
    events = _events(db)
    assert "spend.claim" in events and "spend.ok" in events


@pytest.mark.asyncio
async def test_definite_value_error_releases_claim(claim_session):
    db = claim_session
    spend = _spend_session(db)
    adapter = AsyncMock()
    adapter.execute_transaction = AsyncMock(side_effect=ValueError("Invalid addresses provided"))
    manager = _manager(db, adapter)

    with pytest.raises(ValueError, match="Invalid addresses"):
        await manager.execute_wallet_transaction(AGENT, CHAIN_ID, TO, Decimal("2.5"), _data(spend.id))

    assert _session_row(db, spend.id).used_ait == Decimal("0")
    wallet = _wallet(db)
    assert wallet.total_spent == Decimal("0")
    assert wallet.transaction_count == 0
    events = _events(db)
    assert "spend.claim" in events and "spend.released" in events
    assert "spend.ok" not in events


@pytest.mark.asyncio
async def test_ambiguous_failure_keeps_claim(claim_session):
    """A post-broadcast failure may have moved funds — the reservation must
    stay so the cap keeps counting it, and the outcome is audited."""
    db = claim_session
    spend = _spend_session(db)
    adapter = AsyncMock()
    adapter.execute_transaction = AsyncMock(side_effect=RuntimeError("rpc timeout"))
    manager = _manager(db, adapter)

    with pytest.raises(RuntimeError, match="rpc timeout"):
        await manager.execute_wallet_transaction(AGENT, CHAIN_ID, TO, Decimal("2.5"), _data(spend.id))

    assert _session_row(db, spend.id).used_ait == Decimal("2.5")
    wallet = _wallet(db)
    assert wallet.total_spent == Decimal("2.5")
    events = _events(db)
    assert "spend.claim" in events and "spend.ambiguous" in events
    assert "spend.ok" not in events and "spend.released" not in events


@pytest.mark.asyncio
async def test_cap_breach_never_reaches_adapter(claim_session):
    db = claim_session
    spend = _spend_session(db, cap="3")
    adapter = AsyncMock()
    adapter.execute_transaction = AsyncMock(return_value={"transaction_hash": "0xtx"})
    manager = _manager(db, adapter)

    with pytest.raises(SpendSessionCapError):
        await manager.execute_wallet_transaction(AGENT, CHAIN_ID, TO, Decimal("4"), _data(spend.id))

    adapter.execute_transaction.assert_not_called()
    assert _session_row(db, spend.id).used_ait == Decimal("0")
    assert _wallet(db).total_spent == Decimal("0")


@pytest.mark.asyncio
async def test_missing_session_id_still_rejected(claim_session):
    db = claim_session
    adapter = AsyncMock()
    manager = _manager(db, adapter)
    with pytest.raises(SpendSessionRequiredError):
        await manager.execute_wallet_transaction(AGENT, CHAIN_ID, TO, Decimal("1"), {"ref": "x"})
    adapter.execute_transaction.assert_not_called()
