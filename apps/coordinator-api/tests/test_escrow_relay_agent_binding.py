"""Escrow relay agent_id binding (AGENT-SPEND-D-1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlmodel import Session, select

from aitbc.auth import create_access_token

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity, ChainType, CrossChainMapping
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.payments.domain.escrow_relay import EscrowRelay

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
BUYER_AGENT = "buyer-agent-1"
PROVIDER_AGENT = "provider-agent-1"

PATCH_TARGET = "coordinator_api.contexts.payments.services.escrow_relay.AsyncAITBCHTTPClient"


def _payload(**overrides) -> dict:
    base = {
        "job_id": "mkt_bind_1",
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": "1.0",
        "buyer_agent_id": BUYER_AGENT,
        "provider_agent_id": PROVIDER_AGENT,
        "lock_tx": {
            "type": "ESCROW_LOCK",
            "from": BUYER,
            "to": "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01",
            "amount": 36_000_000,
            "nonce": 1,
            "signature": "0xdeadbeef",
            "payload": {"job_id": "mkt_bind_1", "provider": PROVIDER},
        },
    }
    base.update(overrides)
    return base


def _seed_mappings(db_session: Session, user_id: str = "bind-client-1") -> None:
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


def _token(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, 'client')}"}


class TestEscrowRelayAgentBinding:
    def test_relay_stores_agent_binding(self, client, db_session):
        user_id = "bind-client-happy"
        _seed_mappings(db_session, user_id)
        mock_client = AsyncMock()
        mock_client.post.return_value = {"contract_id": "0xc1", "success": True}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(), headers=_token(user_id))
        assert resp.status_code == 200, resp.text
        sent = mock_client.post.call_args.kwargs["json"]
        assert sent["buyer_agent_id"] == BUYER_AGENT
        assert sent["provider_agent_id"] == PROVIDER_AGENT
        row = db_session.exec(select(EscrowRelay)).first()
        assert row is not None
        assert row.buyer_agent_id == BUYER_AGENT
        assert row.provider_agent_id == PROVIDER_AGENT

    def test_relay_rejects_buyer_address_mismatch(self, client, db_session):
        user_id = "bind-client-mismatch"
        _seed_mappings(db_session, user_id)
        mock_client = AsyncMock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post(
                "/v1/escrow/relay",
                json=_payload(buyer="0x11cD222222eF3496344cFA78fe025c3B48Caf435"),
                headers=_token(user_id),
            )
        assert resp.status_code == 400
        mock_client.post.assert_not_called()

    def test_relay_unknown_agent_404(self, client, db_session):
        user_id = "bind-client-unknown"
        if db_session.get(User, user_id) is None:
            db_session.add(User(id=user_id, email=f"{user_id}@example.com", username=user_id))
        db_session.add(Wallet(user_id=user_id, address=BUYER.lower()))
        db_session.commit()
        mock_client = AsyncMock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(), headers=_token(user_id))
        assert resp.status_code == 404
        mock_client.post.assert_not_called()
