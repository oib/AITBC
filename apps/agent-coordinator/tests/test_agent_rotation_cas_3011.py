"""#3011 AUDIT-AGENT-ROTATION-CAS-1 pins — compare-and-swap on rotation.

``rotate_agent_identity`` verified both proofs against ``old_address``
resolved in ``_rotation_guards``, then awaited ``_consume_identity_nonce``
before ``update_agent_identity`` swapped the binding under the registry
lock — which only checked the agent exists. Two concurrent rotations could
both pass the guards and the slower one committed a stale authorization
after the binding had already moved.

``update_agent_identity`` now takes ``expected_old_address`` and
re-checks the binding under the lock: a mismatch answers ``"conflict"``
without touching registry state, and the route maps it to 409.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("eth_account", reason="wallet-login tests need eth-account")
pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from eth_account import Account  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app.routers import agents as agents_router  # noqa: E402
from agent_app.routers import agent_auth as agent_auth_router  # noqa: E402
from agent_app.routing.agent_discovery import AgentInfo, AgentRegistry, AgentStatus, AgentType  # noqa: E402
from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402
from agent_app.services import nonce_store  # noqa: E402

from aitbc.crypto.agent_envelope import (  # noqa: E402
    identity_claim,
    rotation_claim,
    sign_identity_claim,
    sign_rotation_claim,
)

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
OTHER_KEY = "0x" + "43" * 32
OTHER_ACCOUNT = Account.from_key(OTHER_KEY)
THIRD_KEY = "0x" + "44" * 32
THIRD_ACCOUNT = Account.from_key(THIRD_KEY)
CHAIN_ID = "ait-test-chain"


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def client(monkeypatch, registry):
    app = FastAPI()
    app.include_router(agents_router.router, prefix="/v1")
    app.include_router(agent_auth_router.router)
    fake_state = MagicMock(agent_registry=registry, message_storage=MagicMock())
    for module in (agents_router, agent_auth_router, agent_auth_svc):
        monkeypatch.setattr(module, "state", fake_state)
    return TestClient(app)


def _issue_reg_nonce(client: TestClient, agent_id: str) -> str:
    resp = client.get(f"/v1/agents/nonce?agent_id={agent_id}")
    assert resp.status_code == 200
    return resp.json()["nonce"]


def _register_bound(client: TestClient, agent_id: str, account) -> None:
    nonce = _issue_reg_nonce(client, agent_id)
    registered_at = datetime.now(UTC).isoformat()
    claim = identity_claim(
        agent_id=agent_id,
        identity_address=account.address,
        chain_id=CHAIN_ID,
        nonce=nonce,
        registered_at=registered_at,
    )
    resp = client.post(
        "/v1/agents/register",
        json={
            "agent_id": agent_id,
            "agent_type": "worker",
            "identity_address": account.address,
            "identity_proof": sign_identity_claim(claim, account.key.hex()),
            "identity_nonce": nonce,
            "registered_at": registered_at,
            "chain_id": CHAIN_ID,
        },
    )
    assert resp.status_code == 200, resp.text


def _rotate(client: TestClient, agent_id: str, old_account, new_account):
    """PUT the rotation endpoint; returns the raw response."""
    nonce = _issue_reg_nonce(client, agent_id)
    rotation_ts = datetime.now(UTC).isoformat()
    registered_at = datetime.now(UTC).isoformat()
    new_claim = identity_claim(
        agent_id=agent_id,
        identity_address=new_account.address,
        chain_id=CHAIN_ID,
        nonce=nonce,
        registered_at=registered_at,
    )
    rot_claim = rotation_claim(
        agent_id=agent_id,
        old_address=old_account.address,
        new_address=new_account.address,
        timestamp=rotation_ts,
    )
    return client.put(
        f"/v1/agents/{agent_id}/identity",
        json={
            "new_address": new_account.address,
            "new_proof": sign_identity_claim(new_claim, new_account.key.hex()),
            "rotation_proof": sign_rotation_claim(rot_claim, old_account.key.hex()),
            "identity_nonce": nonce,
            "registered_at": registered_at,
            "rotation_timestamp": rotation_ts,
            "chain_id": CHAIN_ID,
        },
    )


def _bound_agent(agent_id: str, account) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        agent_type=AgentType.WORKER,
        status=AgentStatus.ACTIVE,
        capabilities=[],
        services=[],
        endpoints={},
        metadata={},
        last_heartbeat=datetime.now(UTC),
        registration_time=datetime.now(UTC),
        chain_id=CHAIN_ID,
        identity_address=account.address,
        registered_proof="proof-1",
    )


class TestRotationCasUnit:
    """Registry-level compare-and-swap: the expected binding is re-checked
    under the lock, so a stale authorization conflicts without mutating
    registry state."""

    @pytest.mark.asyncio
    async def test_stale_expected_binding_conflicts_without_mutation(self, registry):
        assert await registry.register_agent(_bound_agent("agent-cas", ACCOUNT)) is True

        # First rotation commits: ACCOUNT -> OTHER.
        first = await registry.update_agent_identity(
            "agent-cas", OTHER_ACCOUNT.address, "proof-2", expected_old_address=ACCOUNT.address
        )
        assert first == "updated"
        assert registry.agents["agent-cas"].identity_address == OTHER_ACCOUNT.address

        # A second rotation authorized against the *old* ACCOUNT binding
        # must conflict — and must not touch the current OTHER binding.
        stale = await registry.update_agent_identity(
            "agent-cas", THIRD_ACCOUNT.address, "proof-3", expected_old_address=ACCOUNT.address
        )
        assert stale == "conflict"
        assert registry.agents["agent-cas"].identity_address == OTHER_ACCOUNT.address
        assert registry.agents["agent-cas"].registered_proof == "proof-2"

    @pytest.mark.asyncio
    async def test_matching_expected_binding_still_updates(self, registry):
        await registry.register_agent(_bound_agent("agent-cas2", ACCOUNT))
        result = await registry.update_agent_identity(
            "agent-cas2", OTHER_ACCOUNT.address, "proof-2", expected_old_address=ACCOUNT.address
        )
        assert result == "updated"
        assert registry.agents["agent-cas2"].identity_address == OTHER_ACCOUNT.address


class TestRotationCasRoute:
    """Route-level: a competing rotation landing inside the nonce-await
    window must turn the slower request's commit into a 409, leaving the
    winner's binding intact."""

    def test_concurrent_rotation_conflicts_and_keeps_winner(self, client, registry, monkeypatch):
        agent_id = "agent-race"
        _register_bound(client, agent_id, ACCOUNT)

        real_consume = agents_router._consume_identity_nonce
        raced = {"done": False}

        async def _consume_with_competing_rotation(agent_id_arg: str, nonce: str | None) -> None:
            # The interleaving window: after the guards verified proofs
            # against ACCOUNT but before this request commits, a competing
            # rotation ACCOUNT -> OTHER lands first.
            await real_consume(agent_id_arg, nonce)
            if not raced["done"]:
                raced["done"] = True
                result = await registry.update_agent_identity(
                    agent_id,
                    OTHER_ACCOUNT.address,
                    "competing-proof",
                    expected_old_address=ACCOUNT.address,
                )
                assert result == "updated"

        monkeypatch.setattr(agents_router, "_consume_identity_nonce", _consume_with_competing_rotation)

        # This request was authorized for ACCOUNT -> THIRD; by commit time
        # the binding is OTHER, so the CAS must refuse it.
        resp = _rotate(client, agent_id, ACCOUNT, THIRD_ACCOUNT)
        assert resp.status_code == 409, resp.text
        assert registry.agents[agent_id].identity_address == OTHER_ACCOUNT.address

    def test_sequential_rotation_still_succeeds(self, client, registry):
        """Control: a matching expected binding still permits authorized
        rotation end-to-end."""
        agent_id = "agent-seq"
        _register_bound(client, agent_id, ACCOUNT)
        resp = _rotate(client, agent_id, ACCOUNT, OTHER_ACCOUNT)
        assert resp.status_code == 200, resp.text
        assert registry.agents[agent_id].identity_address == OTHER_ACCOUNT.address
