"""GPU purchase agent_id binding (AGENT-SPEND-D-1)."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity, ChainType, CrossChainMapping
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.payments.services.payments import PaymentService

from test_routers_market_gpu import _seed_energy

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
BUYER_AGENT = "gpu-buyer-agent-1"
PROVIDER_AGENT = "gpu-provider-agent-1"


def _seed_mappings(db_session: Session, user_id: str = "client1") -> None:
    if db_session.get(User, user_id) is None:
        db_session.add(User(id=user_id, email=f"{user_id}@example.com", username=user_id))
    if not db_session.exec(select(Wallet).where(Wallet.user_id == user_id)).first():
        db_session.add(Wallet(user_id=user_id, address=BUYER.lower()))
    if db_session.exec(select(AgentIdentity).where(AgentIdentity.agent_id == BUYER_AGENT)).first() is None:
        db_session.add(AgentIdentity(agent_id=BUYER_AGENT, owner_address=BUYER.lower()))
    if db_session.exec(select(AgentIdentity).where(AgentIdentity.agent_id == PROVIDER_AGENT)).first() is None:
        db_session.add(AgentIdentity(agent_id=PROVIDER_AGENT, owner_address=PROVIDER.lower()))
    if not db_session.exec(
        select(CrossChainMapping).where(CrossChainMapping.agent_id == BUYER_AGENT, CrossChainMapping.chain_id == 1)
    ).first():
        db_session.add(
            CrossChainMapping(agent_id=BUYER_AGENT, chain_id=1, chain_type=ChainType.ETHEREUM, chain_address=BUYER.lower())
        )
    if not db_session.exec(
        select(CrossChainMapping).where(CrossChainMapping.agent_id == PROVIDER_AGENT, CrossChainMapping.chain_id == 1)
    ).first():
        db_session.add(
            CrossChainMapping(
                agent_id=PROVIDER_AGENT, chain_id=1, chain_type=ChainType.ETHEREUM, chain_address=PROVIDER.lower()
            )
        )
    db_session.commit()


@pytest.mark.unit
def test_gpu_quote_uses_resolved_buyer_in_energy_quote(
    client, db_session, native_pricing, available_gpu, pricing_engine_override, monkeypatch
):
    _seed_energy(db_session)
    _seed_mappings(db_session)
    resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": "client1",
            "buyer_agent_id": BUYER_AGENT,
            "gpu_id": available_gpu,
            "duration_hours": 1.0,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert resp.status_code == 200, resp.text
    quote = resp.json()["energy_quote"]
    assert quote["buyer"].lower() == BUYER.lower()


@pytest.mark.unit
def test_gpu_purchase_forwards_agent_ids_to_payment(
    client,
    client_token,
    db_session,
    native_pricing,
    available_gpu,
    pricing_engine_override,
    monkeypatch,
):
    _seed_energy(db_session)
    _seed_mappings(db_session)
    quote_resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": "client1",
            "buyer_agent_id": BUYER_AGENT,
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert quote_resp.status_code == 200
    quote = quote_resp.json()
    captured = {}

    async def fake_create_payment(self, client_id: str, job_id: str, payment_data):
        captured["payment_data"] = payment_data
        from aitbc_shared import JobPayment

        return JobPayment(
            id="pay_gpu_agent",
            job_id=job_id,
            amount=payment_data.amount,
            status="escrowed",
            currency="AITBC",
            payment_method="aitbc_token",
        )

    monkeypatch.setattr(PaymentService, "create_payment", fake_create_payment)

    buy_resp = client.post(
        "/v1/market/gpu/purchase",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": "client1",
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "payment_method": "blockchain",
            "energy_quote": quote["energy_quote"],
            "protected": True,
            "job_id": quote["job_id"],
            "buyer_address": BUYER,
            "provider_address": PROVIDER,
            "buyer_agent_id": BUYER_AGENT,
            "provider_agent_id": PROVIDER_AGENT,
            "buyer_lock_signature": "0xdeadbeef",
            "buyer_lock_nonce": 1,
        },
    )
    assert buy_resp.status_code == 200, buy_resp.text
    pd = captured.get("payment_data")
    assert pd is not None
    assert pd.buyer_agent_id == BUYER_AGENT
    assert pd.provider_agent_id == PROVIDER_AGENT
