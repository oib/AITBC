"""Coverage for escrow_agent_binding (#1289 residual).

Security-critical binding: resolves agent_id -> payment address and
asserts a caller-supplied payment address matches the resolved one before
escrow lock. Wrong/missing bindings must fail closed (404/400), never
silently pass.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from coordinator_api.contexts.agent_identity.domain.agent_identity import CrossChainMapping
from coordinator_api.contexts.payments.services import escrow_agent_binding as binding

ADDR_A = "0x000000000000000000000000000000000000dEaD"
ADDR_B = "0x000000000000000000000000000000000000bEEF"
ADDR_A_CHECKSUM = "0x000000000000000000000000000000000000dEaD"


def _mapping(agent_id: str = "agent-1", chain_id: int = 1, address: str = ADDR_A) -> CrossChainMapping:
    return CrossChainMapping(agent_id=agent_id, chain_id=chain_id, chain_address=address)


@pytest.mark.unit
def test_resolve_returns_canonical_address(db_session: Session):
    db_session.add(_mapping())
    db_session.commit()
    resolved = binding.resolve_agent_payment_address_sync(db_session, "agent-1", chain_id=1)
    assert resolved == binding.canonical_address(ADDR_A)


@pytest.mark.unit
def test_resolve_missing_agent_404(db_session: Session):
    with pytest.raises(HTTPException) as exc:
        binding.resolve_agent_payment_address_sync(db_session, "ghost", chain_id=1)
    assert exc.value.status_code == 404


@pytest.mark.unit
def test_resolve_wrong_chain_404(db_session: Session):
    db_session.add(_mapping(chain_id=1))
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        binding.resolve_agent_payment_address_sync(db_session, "agent-1", chain_id=999)
    assert exc.value.status_code == 404


@pytest.mark.unit
def test_resolve_mapping_without_address_404(db_session: Session):
    db_session.add(CrossChainMapping(agent_id="agent-1", chain_id=1, chain_address=""))
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        binding.resolve_agent_payment_address_sync(db_session, "agent-1", chain_id=1)
    assert exc.value.status_code == 404


@pytest.mark.unit
def test_default_resolve_chain_id_parsing(monkeypatch):
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "native_chain_id", "137")
    assert binding.default_resolve_chain_id() == 137
    monkeypatch.setattr(settings, "native_chain_id", "not-a-number")
    monkeypatch.setenv("CHAIN_ID", "")
    assert binding.default_resolve_chain_id() == 1


@pytest.mark.asyncio
async def test_assert_binding_accepts_matching_address(db_session: Session, monkeypatch):
    async def _fake_resolve(session, agent_id, chain_id=None):
        return ADDR_A_CHECKSUM

    monkeypatch.setattr(binding, "resolve_agent_payment_address", _fake_resolve)
    await binding.assert_agent_address_binding(
        db_session, "agent-1", "0x000000000000000000000000000000000000dead", role="buyer"
    )


@pytest.mark.asyncio
async def test_assert_binding_rejects_mismatched_address(db_session: Session, monkeypatch):
    async def _fake_resolve(session, agent_id, chain_id=None):
        return ADDR_A_CHECKSUM

    monkeypatch.setattr(binding, "resolve_agent_payment_address", _fake_resolve)
    with pytest.raises(HTTPException) as exc:
        await binding.assert_agent_address_binding(db_session, "agent-1", ADDR_B, role="buyer")
    assert exc.value.status_code == 400
    assert "buyer" in exc.value.detail


@pytest.mark.asyncio
async def test_assert_binding_propagates_resolve_404(db_session: Session, monkeypatch):
    async def _fake_resolve(session, agent_id, chain_id=None):
        raise HTTPException(status_code=404, detail="no payment address")

    monkeypatch.setattr(binding, "resolve_agent_payment_address", _fake_resolve)
    with pytest.raises(HTTPException) as exc:
        await binding.assert_agent_address_binding(db_session, "ghost", ADDR_A, role="seller")
    assert exc.value.status_code == 404
