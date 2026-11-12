"""#1884 pins: escrow metadata reads are party-or-admin scoped.

Pre-fix (with #1880's auth floor): any authenticated principal could read
``GET /v1/tasks/escrow/{id}`` and ``GET /v1/tasks/{task_id}/escrow`` —
requester/agent/amount/tx-hash metadata enumerable across parties. Now the
principal's registry-bound wallet must match ``requester`` or ``agent``
(admins bypass); aggregate reads stay any-principal.
"""

from __future__ import annotations

import os
import uuid
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

from agent_app.config import settings  # noqa: E402
from agent_app.routers import agents as agents_router  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402
from agent_app.routing.agent_discovery import AgentRegistry  # noqa: E402
from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402
from agent_app.services import nonce_store  # noqa: E402

from aitbc.crypto import PaymentEscrow  # noqa: E402
from aitbc.crypto.agent_envelope import identity_claim, request_claim, sign_identity_claim, sign_request_claim  # noqa: E402

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
OTHER_KEY = "0x" + "43" * 32
OTHER_ACCOUNT = Account.from_key(OTHER_KEY)
CHAIN_ID = "ait-test-chain"
OPERATOR_KEY = "test-operator-key-1884"
REQUESTER_ADDR = "0x" + "11" * 20


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


@pytest.fixture
def fake_state():
    state = MagicMock()
    state.agent_registry = AgentRegistry()
    state.payment_escrow = PaymentEscrow()
    state.escrow_rpc = MagicMock()
    return state


@pytest.fixture
def client(monkeypatch, fake_state):
    monkeypatch.setenv("COORDINATOR_API_KEY", OPERATOR_KEY)
    app = FastAPI()
    app.include_router(agents_router.router, prefix="/v1")
    app.include_router(tasks_router.router, prefix="/v1")
    monkeypatch.setattr(tasks_router, "state", fake_state)
    monkeypatch.setattr(agents_router, "state", fake_state)
    monkeypatch.setattr(agent_auth_svc, "state", fake_state)
    return TestClient(app)


@pytest.fixture
def enforce(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
    return client


def _registration_fields(agent_id: str, account, nonce: str) -> dict:
    registered_at = datetime.now(UTC).isoformat()
    claim = identity_claim(
        agent_id=agent_id,
        identity_address=account.address,
        chain_id=CHAIN_ID,
        nonce=nonce,
        registered_at=registered_at,
    )
    return {
        "identity_address": account.address,
        "identity_proof": sign_identity_claim(claim, account.key.hex()),
        "identity_nonce": nonce,
        "registered_at": registered_at,
        "chain_id": CHAIN_ID,
    }


def _signed_headers(agent_id: str, account) -> dict[str, str]:
    ts = datetime.now(UTC).isoformat()
    nc = uuid.uuid4().hex
    claim = request_claim(agent_id=agent_id, timestamp=ts, nonce=nc)
    return {
        "X-Agent-Id": agent_id,
        "X-Agent-Timestamp": ts,
        "X-Agent-Nonce": nc,
        "X-Agent-Signature": sign_request_claim(claim, account.key.hex()),
    }


def _register_bound(client: TestClient, agent_id: str, account) -> None:
    resp = client.get(f"/v1/agents/nonce?agent_id={agent_id}")
    assert resp.status_code == 200, resp.text
    nonce = resp.json()["nonce"]
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


def _seed_escrow(fake_state, *, agent_addr: str, requester_addr: str = REQUESTER_ADDR) -> tuple[str, str]:
    entry = fake_state.payment_escrow.create_escrow(
        task_id=f"task-{uuid.uuid4().hex[:6]}",
        chain_id=CHAIN_ID,
        requester=requester_addr,
        agent=agent_addr,
        amount=100,
        fee=1,
    )
    return entry.escrow_id, entry.task_id


class TestEscrowReadPartyScope:
    def test_anonymous_401(self, enforce, fake_state):
        escrow_id, task_id = _seed_escrow(fake_state, agent_addr=ACCOUNT.address)
        assert enforce.get(f"/v1/tasks/escrow/{escrow_id}").status_code == 401
        assert enforce.get(f"/v1/tasks/{task_id}/escrow").status_code == 401

    def test_foreign_agent_403(self, enforce, fake_state):
        """A bound agent whose wallet is neither party gets 403 in enforce."""
        escrow_id, task_id = _seed_escrow(fake_state, agent_addr=ACCOUNT.address)
        _register_bound(enforce, "agent-other", OTHER_ACCOUNT)
        h1 = _signed_headers("agent-other", OTHER_ACCOUNT)
        h2 = _signed_headers("agent-other", OTHER_ACCOUNT)
        assert enforce.get(f"/v1/tasks/escrow/{escrow_id}", headers=h1).status_code == 403
        assert enforce.get(f"/v1/tasks/{task_id}/escrow", headers=h2).status_code == 403

    def test_party_agent_reads_200(self, enforce, fake_state):
        """The escrow's provider agent (entry.agent) may read its own escrow."""
        escrow_id, task_id = _seed_escrow(fake_state, agent_addr=ACCOUNT.address)
        _register_bound(enforce, "agent-payee", ACCOUNT)
        r1 = enforce.get(f"/v1/tasks/escrow/{escrow_id}", headers=_signed_headers("agent-payee", ACCOUNT))
        r2 = enforce.get(f"/v1/tasks/{task_id}/escrow", headers=_signed_headers("agent-payee", ACCOUNT))
        assert r1.status_code == 200 and r1.json()["escrow"]["escrow_id"] == escrow_id
        assert r2.status_code == 200 and r2.json()["escrow"]["task_id"] == task_id

    def test_admin_reads_any_200(self, enforce, fake_state):
        escrow_id, task_id = _seed_escrow(fake_state, agent_addr=OTHER_ACCOUNT.address)
        headers = {"X-Api-Key": OPERATOR_KEY}
        assert enforce.get(f"/v1/tasks/escrow/{escrow_id}", headers=headers).status_code == 200
        assert enforce.get(f"/v1/tasks/{task_id}/escrow", headers=headers).status_code == 200

    def test_aggregate_reads_stay_any_principal(self, enforce, fake_state):
        """status/queues/stats/escrow-config are not party-scoped."""
        fake_state.task_distributor = MagicMock()
        fake_state.task_distributor.get_distribution_stats = MagicMock(return_value={})
        fake_state.task_distributor.get_queue_sizes = MagicMock(return_value={})
        _register_bound(enforce, "agent-any", OTHER_ACCOUNT)
        for path in ("/v1/tasks/status", "/v1/tasks/queues", "/v1/tasks/queues/stats"):
            r = enforce.get(path, headers=_signed_headers("agent-any", OTHER_ACCOUNT))
            assert r.status_code == 200, f"{path}: {r.status_code} {r.text}"
