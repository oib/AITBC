"""Phase C tests — server-side authorization + signature-scheme reconciliation.

Covers:

* Admin/operator gates — broadcast, load-balancer strategy/stats, peers
  add/remove/read, registry stats, escrow expire-stale, queue clear: 401 for
  anonymous callers and 403 for non-admin principals in ``enforce``; open in
  ``advisory``/``disabled``.
* Agent-scoped routes — ``PUT /v1/agents/{id}/status``,
  ``POST /v1/agents/{id}/heartbeat``, ``POST /api/v1/agent/keys/register``:
  the bound agent (JWT or ``X-Agent-*`` headers) passes, other agents 403.
* ``POST /v1/tasks/submit`` — enforce requires a principal; a payment without
  a lock anchor stays ``pending`` rather than stamping a bookkeeping "locked".
* complete/fail — both the legacy ``signature``/``signed_at`` form and the
  Phase-B3 ``agent_signature`` (req-v1) form are accepted; wrong-key and
  replayed proofs 403.
* ``request_coins_handler`` — enforce binds ``wallet_address`` to the
  connection's authenticated wallet.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)
os.environ["AITBC_ENABLE_RATE_LIMITING"] = "false"

pytest.importorskip("eth_account", reason="wallet-login tests need eth-account")
pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from eth_account import Account  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app.config import settings  # noqa: E402
from agent_app.encryption import public_keys  # noqa: E402
from agent_app.routers import agent_auth as agent_auth_router  # noqa: E402
from agent_app.routers import agents as agents_router  # noqa: E402
from agent_app.routers import keys as keys_router  # noqa: E402
from agent_app.routers import messages as messages_router  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402
from agent_app.routers import websocket as websocket_router  # noqa: E402
from agent_app.routing.agent_discovery import AgentRegistry  # noqa: E402
from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402
from agent_app.services import nonce_store  # noqa: E402
from agent_app.websocket import agent_stream  # noqa: E402

from aitbc.auth.jwt import create_access_token  # noqa: E402
from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402
from aitbc.crypto.agent_envelope import (  # noqa: E402
    AGENT_REQ_DOMAIN,
    domain_digest,
    identity_claim,
    login_claim,
    request_claim,
    sign_identity_claim,
    sign_login_claim,
    sign_request_claim,
)
from aitbc.crypto.crypto import sign_transaction_hash  # noqa: E402

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
OTHER_KEY = "0x" + "43" * 32
OTHER_ACCOUNT = Account.from_key(OTHER_KEY)
CHAIN_ID = "ait-test-chain"
OPERATOR_KEY = "test-operator-key"


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #


def _registration_fields(agent_id: str, account, nonce: str, chain_id: str = CHAIN_ID) -> dict:
    registered_at = datetime.now(UTC).isoformat()
    claim = identity_claim(
        agent_id=agent_id,
        identity_address=account.address,
        chain_id=chain_id,
        nonce=nonce,
        registered_at=registered_at,
    )
    return {
        "identity_address": account.address,
        "identity_proof": sign_identity_claim(claim, account.key.hex()),
        "identity_nonce": nonce,
        "registered_at": registered_at,
        "chain_id": chain_id,
    }


def _signed_headers(agent_id: str, account, nonce: str | None = None) -> dict[str, str]:
    ts = datetime.now(UTC).isoformat()
    nc = nonce or uuid.uuid4().hex
    claim = request_claim(agent_id=agent_id, timestamp=ts, nonce=nc)
    return {
        "X-Agent-Id": agent_id,
        "X-Agent-Timestamp": ts,
        "X-Agent-Nonce": nc,
        "X-Agent-Signature": sign_request_claim(claim, account.key.hex()),
    }


def _req_v1_signature(task_id: str, pk: str, timestamp: str, nonce: str, **extra) -> str:
    """The Phase-B3 body signature: req-v1 over {"task_id","timestamp","nonce",...}."""
    payload: dict = {"task_id": task_id, "timestamp": timestamp, "nonce": nonce}
    payload.update(extra)
    return "0x" + sign_transaction_hash(domain_digest(payload, AGENT_REQ_DOMAIN).hex(), pk).removeprefix("0x")


def _legacy_signature(action: str, task_id: str, pk: str, signed_at: int, **extra) -> str:
    from aitbc.crypto.crypto import sign_transaction_data

    fields: dict = {"action": action, "task_id": task_id, "signed_at": signed_at}
    fields.update(extra)
    return sign_transaction_data(fields, pk)


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


@pytest.fixture(autouse=True)
def _clear_key_registry():
    public_keys.PUBLIC_KEY_REGISTRY.clear()
    yield
    public_keys.PUBLIC_KEY_REGISTRY.clear()


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def fake_state(registry):
    """Shared coordinator state: real registry, mocked periphery."""
    state = MagicMock()
    state.agent_registry = registry
    state.message_storage = MagicMock()
    state.message_storage.store_message = AsyncMock(return_value=True)
    state.message_storage.get_message = AsyncMock(return_value=None)
    state.message_storage.get_messages_by_receiver = AsyncMock(return_value=[])
    state.message_storage.get_messages_by_sender = AsyncMock(return_value=[])
    state.message_storage.get_all_messages = AsyncMock(return_value=[])
    state.message_storage.get_message_count = AsyncMock(return_value=0)
    state.peer_storage = MagicMock()
    state.peer_storage.add_peer = AsyncMock(return_value=True)
    state.peer_storage.remove_peer = AsyncMock(return_value=True)
    state.peer_storage.get_agent_peers = AsyncMock(return_value=[{"peer_id": "p-1"}])
    state.peer_storage.get_all_peer_connections = AsyncMock(return_value={"a": ["b"]})
    state.task_distributor = MagicMock()
    state.task_distributor.submit_task = AsyncMock(return_value=True)
    state.task_distributor.clear_queue = AsyncMock(return_value=3)
    state.task_distributor.get_distribution_stats = MagicMock(return_value={})
    state.task_distributor.get_queue_sizes = MagicMock(return_value={"high": 1})
    state.load_balancer = MagicMock()
    state.load_balancer.get_load_balancing_stats = MagicMock(return_value={"strategy": "least_connections"})
    state.load_balancer.set_strategy = MagicMock()
    state.communication_manager = MagicMock()
    state.communication_manager.send_message = AsyncMock(return_value=True)
    state.payment_escrow = None
    state.escrow_rpc = None
    return state


@pytest.fixture
def client(monkeypatch, fake_state):
    """TestClient serving the Phase C surface over the shared fake state."""
    monkeypatch.setenv("COORDINATOR_API_KEY", OPERATOR_KEY)
    app = FastAPI()
    app.include_router(agents_router.router, prefix="/v1")
    app.include_router(agent_auth_router.router)
    app.include_router(messages_router.router)
    app.include_router(tasks_router.router, prefix="/v1")
    app.include_router(keys_router.router)
    app.include_router(websocket_router.router)
    for module in (agents_router, agent_auth_router, messages_router, tasks_router, agent_auth_svc):
        monkeypatch.setattr(module, "state", fake_state)
    return TestClient(app)


@pytest.fixture
def enforce(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
    return client


def _issue_reg_nonce(client: TestClient, agent_id: str) -> str:
    resp = client.get(f"/v1/agents/nonce?agent_id={agent_id}")
    assert resp.status_code == 200
    return resp.json()["nonce"]


def _register_bound(client: TestClient, agent_id: str, account) -> None:
    nonce = _issue_reg_nonce(client, agent_id)
    resp = client.post(
        "/v1/agents/register",
        json={"agent_id": agent_id, "agent_type": "worker", **_registration_fields(agent_id, account, nonce)},
    )
    assert resp.status_code == 200, resp.text


def _login(client: TestClient, agent_id: str, account) -> str:
    resp = client.post(f"/api/v1/agent/auth/nonce?agent_id={agent_id}")
    assert resp.status_code == 200
    body = resp.json()
    claim = login_claim(agent_id=agent_id, wallet_address=account.address, chain_id=body["chain_id"], nonce=body["nonce"])
    resp = client.post(
        "/api/v1/agent/auth/login",
        json={
            "agent_id": agent_id,
            "wallet_address": account.address,
            "nonce": body["nonce"],
            "signature": sign_login_claim(claim, account.key.hex()),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _admin_headers() -> dict[str, str]:
    return {"X-Api-Key": OPERATOR_KEY}


class _FakeAgent:
    """Minimal discovery result for the broadcast route."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id

    def to_dict(self) -> dict:
        return {"agent_id": self.agent_id}


# --------------------------------------------------------------------------- #
# Admin/operator gates (enforce)
# --------------------------------------------------------------------------- #


class TestAdminRouteGates:
    """Every route in the Phase C operator surface: 401 anonymous, 403 agent,
    200 operator — enforce mode only; advisory/disabled stay open."""

    ADMIN_CALLS = [
        ("POST", "/api/v1/agent/messages/broadcast", {"json": {"message_type": "direct", "payload": {"a": 1}}}),
        ("PUT", "/api/v1/agent/messages/load-balancer/strategy?strategy=round_robin", {}),
        ("POST", "/api/v1/agent/messages/peers/add?agent_id=a1&peer_id=p1", {}),
        ("POST", "/api/v1/agent/messages/peers/remove?agent_id=a1&peer_id=p1", {}),
        ("GET", "/api/v1/agent/messages/peers", {}),
        ("GET", "/api/v1/agent/messages/peers/a1", {}),
        ("GET", "/api/v1/agent/messages/load-balancer/stats", {}),
        ("GET", "/api/v1/agent/messages/registry/stats", {}),
        ("POST", "/v1/tasks/escrow/expire-stale", {}),
        ("POST", "/v1/tasks/queues/high/clear", {}),
    ]

    def _call(self, client: TestClient, method: str, url: str, kwargs: dict, headers: dict | None = None):
        return client.request(method, url, headers=headers or {}, **kwargs)

    @pytest.mark.parametrize("method,url,kwargs", ADMIN_CALLS)
    def test_enforce_anonymous_401(self, enforce, fake_state, method, url, kwargs):
        fake_state.payment_escrow = PaymentEscrow()
        resp = self._call(enforce, method, url, kwargs)
        assert resp.status_code == 401, f"{method} {url}: {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", ADMIN_CALLS)
    def test_enforce_agent_principal_403(self, enforce, fake_state, method, url, kwargs):
        """A bound agent principal is not an operator."""
        fake_state.payment_escrow = PaymentEscrow()
        _register_bound(enforce, "agent-1", ACCOUNT)
        headers = _signed_headers("agent-1", ACCOUNT)
        resp = self._call(enforce, method, url, kwargs, headers=headers)
        assert resp.status_code == 403, f"{method} {url}: {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", ADMIN_CALLS)
    def test_enforce_operator_ok(self, enforce, fake_state, method, url, kwargs):
        fake_state.payment_escrow = PaymentEscrow()
        fake_state.agent_registry.discover_agents = AsyncMock(return_value=[])
        resp = self._call(enforce, method, url, kwargs, headers=_admin_headers())
        assert resp.status_code == 200, f"{method} {url}: {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", ADMIN_CALLS)
    def test_disabled_stays_open(self, client, fake_state, monkeypatch, method, url, kwargs):
        """The deployed default: no credential, no rejection."""
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        fake_state.payment_escrow = PaymentEscrow()
        fake_state.agent_registry.discover_agents = AsyncMock(return_value=[])
        resp = self._call(client, method, url, kwargs)
        assert resp.status_code == 200, f"{method} {url}: {resp.text}"

    def test_advisory_anonymous_allowed(self, client, fake_state, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        fake_state.agent_registry.discover_agents = AsyncMock(return_value=[])
        resp = client.post("/api/v1/agent/messages/broadcast", json={"message_type": "direct", "payload": {"a": 1}})
        assert resp.status_code == 200

    def test_advisory_non_admin_allowed(self, client, fake_state, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/messages/load-balancer/stats", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200


class TestBroadcastDerivedSender:
    """The broadcast sender is the coordinator, whoever the caller is."""

    def test_sender_id_stays_agent_coordinator(self, enforce, fake_state):
        fake_state.agent_registry.discover_agents = AsyncMock(return_value=[_FakeAgent("agent-9")])
        resp = enforce.post(
            "/api/v1/agent/messages/broadcast",
            json={"message_type": "direct", "payload": {"note": "hi"}},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        stored = fake_state.message_storage.store_message.call_args[0][1]
        assert stored["sender_id"] == "agent-coordinator"


# --------------------------------------------------------------------------- #
# Agent-scoped routes: heartbeat, status, key registration
# --------------------------------------------------------------------------- #


class TestAgentScopedRoutes:
    def test_enforce_heartbeat_own_ok(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        resp = enforce.post("/v1/agents/agent-1/heartbeat", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent-1"

    def test_enforce_heartbeat_other_403(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        _register_bound(enforce, "agent-2", OTHER_ACCOUNT)
        resp = enforce.post("/v1/agents/agent-2/heartbeat", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 403

    def test_enforce_heartbeat_anonymous_401(self, enforce):
        resp = enforce.post("/v1/agents/agent-1/heartbeat")
        assert resp.status_code == 401

    def test_enforce_heartbeat_admin_ok(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        resp = enforce.post("/v1/agents/agent-1/heartbeat", headers=_admin_headers())
        assert resp.status_code == 200

    def test_enforce_heartbeat_via_jwt(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        token = _login(enforce, "agent-1", ACCOUNT)
        resp = enforce.post("/v1/agents/agent-1/heartbeat", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_enforce_status_own_ok(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        resp = enforce.put(
            "/v1/agents/agent-1/status",
            json={"status": "busy"},
            headers=_signed_headers("agent-1", ACCOUNT),
        )
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "busy"

    def test_enforce_status_other_403(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        _register_bound(enforce, "agent-2", OTHER_ACCOUNT)
        resp = enforce.put(
            "/v1/agents/agent-2/status",
            json={"status": "busy"},
            headers=_signed_headers("agent-1", ACCOUNT),
        )
        assert resp.status_code == 403

    def test_disabled_heartbeat_open(self, client, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.post("/v1/agents/agent-1/heartbeat")
        assert resp.status_code == 200


class TestKeyRegistration:
    def _body(self, agent_id: str) -> dict:
        import base64

        return {"agent_id": agent_id, "public_key": base64.b64encode(b"fake-rsa-public-key").decode(), "key_id": "k1"}

    def test_enforce_own_key_registers_and_binds_identity(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        resp = enforce.post(
            "/api/v1/agent/keys/register", json=self._body("agent-1"), headers=_signed_headers("agent-1", ACCOUNT)
        )
        assert resp.status_code == 200
        assert public_keys.PUBLIC_KEY_REGISTRY["agent-1"]["identity_address"] == ACCOUNT.address

    def test_enforce_other_agent_403(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        _register_bound(enforce, "agent-2", OTHER_ACCOUNT)
        resp = enforce.post(
            "/api/v1/agent/keys/register", json=self._body("agent-2"), headers=_signed_headers("agent-1", ACCOUNT)
        )
        assert resp.status_code == 403
        assert "agent-2" not in public_keys.PUBLIC_KEY_REGISTRY

    def test_enforce_anonymous_401(self, enforce):
        resp = enforce.post("/api/v1/agent/keys/register", json=self._body("agent-1"))
        assert resp.status_code == 401

    def test_enforce_admin_registers_without_identity(self, enforce):
        resp = enforce.post("/api/v1/agent/keys/register", json=self._body("agent-9"), headers=_admin_headers())
        assert resp.status_code == 200
        assert public_keys.PUBLIC_KEY_REGISTRY["agent-9"]["identity_address"] is None

    def test_enforce_user_jwt_without_wallet_403(self, enforce):
        """A valid non-agent token is a principal but not a bound identity."""
        user_token = create_access_token(user_id="human-1", role="user")
        resp = enforce.post(
            "/api/v1/agent/keys/register",
            json=self._body("human-1"),
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    def test_disabled_register_open(self, client, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        resp = client.post("/api/v1/agent/keys/register", json=self._body("agent-1"))
        assert resp.status_code == 200
        assert public_keys.PUBLIC_KEY_REGISTRY["agent-1"]["identity_address"] is None


# --------------------------------------------------------------------------- #
# POST /v1/tasks/submit — principal gate + pending-vs-locked stamping
# --------------------------------------------------------------------------- #


class TestTaskSubmit:
    def _submission(self, task_id: str, **payment_overrides) -> dict:
        payment = {"requester": "0xBuyer", "agent": "0xAgent", "amount": 100}
        payment.update(payment_overrides)
        return {"task_data": {"task_id": task_id}, "payment": payment}

    def test_enforce_anonymous_401(self, enforce, fake_state):
        resp = enforce.post("/v1/tasks/submit", json={"task_data": {"task_id": "t-anon"}})
        assert resp.status_code == 401

    def test_enforce_agent_jwt_ok(self, enforce, fake_state):
        _register_bound(enforce, "buyer-1", ACCOUNT)
        token = _login(enforce, "buyer-1", ACCOUNT)
        resp = enforce.post(
            "/v1/tasks/submit",
            json={"task_data": {"task_id": "t-jwt"}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "t-jwt"

    def test_enforce_operator_ok(self, enforce, fake_state):
        resp = enforce.post("/v1/tasks/submit", json={"task_data": {"task_id": "t-op"}}, headers=_admin_headers())
        assert resp.status_code == 200

    def test_payment_without_anchor_stays_pending(self, client, fake_state, monkeypatch):
        """A bookkeeping submission must not stamp 'locked' — no lock anchor."""
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
        escrow = PaymentEscrow()
        fake_state.payment_escrow = escrow

        resp = client.post("/v1/tasks/submit", json=self._submission("t-pending"))

        assert resp.status_code == 200
        body = resp.json()
        assert body["escrow_status"] == "pending"
        entry = escrow.get_escrow_for_task("t-pending")
        assert entry is not None
        assert entry.status == EscrowStatus.PENDING
        assert entry.tx_hash_lock is None

    def test_payment_with_lock_tx_locks(self, client, fake_state, monkeypatch):
        """A buyer-signed lock_tx is the anchor — the row goes LOCKED."""
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
        escrow = PaymentEscrow()
        fake_state.payment_escrow = escrow

        class FakeEscrowRPC:
            def create(self, **_kwargs):
                return {"lock_tx_hash": "0x" + "ab" * 32, "contract_id": "contract-1"}

        fake_state.escrow_rpc = FakeEscrowRPC()

        resp = client.post(
            "/v1/tasks/submit",
            json=self._submission("t-locked", lock_tx={"type": "ESCROW_LOCK"}, lock_signature="0xsig"),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["escrow_status"] == "locked"
        assert body["contract_id"] == "contract-1"
        entry = escrow.get_escrow_for_task("t-locked")
        assert entry.status == EscrowStatus.LOCKED
        assert entry.tx_hash_lock == "0x" + "ab" * 32
        assert entry.contract_id == "contract-1"

    def test_no_payment_no_escrow(self, client, fake_state, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        resp = client.post("/v1/tasks/submit", json={"task_data": {"task_id": "t-free"}})
        assert resp.status_code == 200
        assert resp.json()["escrow_id"] is None
        assert resp.json()["escrow_status"] is None


# --------------------------------------------------------------------------- #
# complete/fail — both signature schemes
# --------------------------------------------------------------------------- #


class TestEscrowDualSignature:
    def _client(self, monkeypatch, fake_state):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        escrow = PaymentEscrow()
        fake_state.payment_escrow = escrow
        fake_state.escrow_rpc = None
        return escrow

    def _locked(self, escrow, task_id: str, agent: str, amount: int = 100):
        entry = escrow.create_escrow(task_id=task_id, chain_id="c", requester="0xBuyer", agent=agent, amount=amount)
        escrow.lock(entry.escrow_id)
        return entry

    def test_complete_req_v1_signature_accepted(self, client, fake_state, monkeypatch):
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-rv1", ACCOUNT.address)
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-rv1", PRIVATE_KEY, ts, nonce, amount_units=30)
        resp = client.post(
            "/v1/tasks/t-rv1/complete",
            json={"amount_units": 30, "timestamp": ts, "nonce": nonce, "agent_signature": sig},
        )
        assert resp.status_code == 200, resp.text
        assert escrow.get_escrow_for_task("t-rv1").status == EscrowStatus.RELEASED

    def test_fail_req_v1_signature_accepted(self, client, fake_state, monkeypatch):
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-rv1f", ACCOUNT.address)
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-rv1f", PRIVATE_KEY, ts, nonce, reason="execution_failed")
        resp = client.post(
            "/v1/tasks/t-rv1f/fail",
            json={"reason": "execution_failed", "timestamp": ts, "nonce": nonce, "agent_signature": sig},
        )
        assert resp.status_code == 200, resp.text
        assert escrow.get_escrow_for_task("t-rv1f").status == EscrowStatus.REFUNDED

    def test_complete_legacy_signature_still_accepted(self, client, fake_state, monkeypatch):
        """The 23ad910d6 form keeps working — the executor emits both."""
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-legacy", ACCOUNT.address)
        signed_at = int(time.time())
        sig = _legacy_signature("complete", "t-legacy", PRIVATE_KEY, signed_at, amount_units=40)
        resp = client.post(
            "/v1/tasks/t-legacy/complete",
            json={"amount_units": 40, "signed_at": signed_at, "signature": sig},
        )
        assert resp.status_code == 200, resp.text
        assert escrow.get_escrow_for_task("t-legacy").status == EscrowStatus.RELEASED

    def test_complete_both_forms_accepted(self, client, fake_state, monkeypatch):
        """The exact executor body: legacy signature + req-v1 agent_signature."""
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-both", ACCOUNT.address)
        signed_at = int(time.time())
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        body = {
            "amount_units": 50,
            "signed_at": signed_at,
            "signature": _legacy_signature("complete", "t-both", PRIVATE_KEY, signed_at, amount_units=50),
            "timestamp": ts,
            "nonce": nonce,
            "agent_signature": _req_v1_signature("t-both", PRIVATE_KEY, ts, nonce, amount_units=50),
        }
        resp = client.post("/v1/tasks/t-both/complete", json=body)
        assert resp.status_code == 200, resp.text

    def test_complete_req_v1_wrong_signer_403(self, client, fake_state, monkeypatch):
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-wrong", ACCOUNT.address)
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-wrong", OTHER_KEY, ts, nonce, amount_units=30)
        resp = client.post(
            "/v1/tasks/t-wrong/complete",
            json={"amount_units": 30, "timestamp": ts, "nonce": nonce, "agent_signature": sig},
        )
        assert resp.status_code == 403
        assert escrow.get_escrow_for_task("t-wrong").status == EscrowStatus.LOCKED

    def test_complete_req_v1_tampered_amount_403(self, client, fake_state, monkeypatch):
        """The signature covers amount_units — a different body value must fail."""
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-tamp", ACCOUNT.address)
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-tamp", PRIVATE_KEY, ts, nonce, amount_units=30)
        resp = client.post(
            "/v1/tasks/t-tamp/complete",
            json={"amount_units": 99, "timestamp": ts, "nonce": nonce, "agent_signature": sig},
        )
        assert resp.status_code == 403

    def test_req_v1_replay_403(self, client, fake_state, monkeypatch):
        """A captured agent_signature body cannot be replayed inside the window."""
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-replay", ACCOUNT.address)
        self._locked(escrow, "t-replay2", ACCOUNT.address)
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-replay", PRIVATE_KEY, ts, nonce, amount_units=10)
        body = {"amount_units": 10, "timestamp": ts, "nonce": nonce, "agent_signature": sig}
        assert client.post("/v1/tasks/t-replay/complete", json=body).status_code == 200
        # Same signature over a different task_id cannot verify — and the same
        # nonce under a second task's body is caught by the dedup as well.
        sig2 = _req_v1_signature("t-replay2", PRIVATE_KEY, ts, nonce, amount_units=10)
        body2 = {"amount_units": 10, "timestamp": ts, "nonce": nonce, "agent_signature": sig2}
        resp = client.post("/v1/tasks/t-replay2/complete", json=body2)
        assert resp.status_code == 403

    def test_req_v1_stale_timestamp_403(self, client, fake_state, monkeypatch):
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-stale", ACCOUNT.address)
        ts = "2020-01-01T00:00:00+00:00"
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-stale", PRIVATE_KEY, ts, nonce, amount_units=10)
        resp = client.post(
            "/v1/tasks/t-stale/complete",
            json={"amount_units": 10, "timestamp": ts, "nonce": nonce, "agent_signature": sig},
        )
        assert resp.status_code == 403

    def test_req_v1_missing_fields_403(self, client, fake_state, monkeypatch):
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-partial", ACCOUNT.address)
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-partial", PRIVATE_KEY, ts, nonce, amount_units=10)
        # agent_signature without timestamp/nonce is an incomplete credential.
        resp = client.post("/v1/tasks/t-partial/complete", json={"amount_units": 10, "agent_signature": sig})
        assert resp.status_code == 403

    def test_fail_req_v1_wrong_signer_403(self, client, fake_state, monkeypatch):
        escrow = self._client(monkeypatch, fake_state)
        self._locked(escrow, "t-fwrong", ACCOUNT.address)
        ts = datetime.now(UTC).isoformat()
        nonce = uuid.uuid4().hex
        sig = _req_v1_signature("t-fwrong", OTHER_KEY, ts, nonce, reason="x")
        resp = client.post(
            "/v1/tasks/t-fwrong/fail",
            json={"reason": "x", "timestamp": ts, "nonce": nonce, "agent_signature": sig},
        )
        assert resp.status_code == 403
        assert escrow.get_escrow_for_task("t-fwrong").status == EscrowStatus.LOCKED


# --------------------------------------------------------------------------- #
# request_coins_handler — connection wallet binding
# --------------------------------------------------------------------------- #


class TestRequestCoinsWalletBinding:
    def _manager_with_wallet(self, agent_id: str, wallet: str | None):
        cm = agent_stream.ConnectionManager()
        cm.active_connections[agent_id] = MagicMock()
        if wallet is not None:
            cm.connection_wallets[agent_id] = wallet
        cm.send_personal_message = AsyncMock(return_value=True)
        return cm

    def _msg(self, sender: str, wallet: str, amount: int = 5) -> dict:
        return {
            "sender_id": sender,
            "content": f"REQUEST_COINS {json.dumps({'amount': amount, 'wallet_address': wallet})}",
        }

    def test_enforce_matching_wallet_proceeds(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "none.db"))
        monkeypatch.setattr(agent_stream, "_record_coin_request", lambda *a, **k: None)
        monkeypatch.setattr(
            agent_stream, "_submit_transaction", lambda tx: {"success": True, "transaction_hash": "0x" + "ff" * 32}
        )
        fake_tx = MagicMock()
        fake_tx.generate_signed_transaction = MagicMock(return_value={"signed": True})
        monkeypatch.setattr(agent_stream, "TransactionService", lambda: fake_tx)

        cm = self._manager_with_wallet("agent-1", ACCOUNT.address)

        result = asyncio.run(agent_stream.request_coins_handler(self._msg("agent-1", ACCOUNT.address), cm, MagicMock()))
        assert result["action"] == "coins_transferred"
        assert result["wallet_address"] == ACCOUNT.address

    def test_enforce_other_wallet_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "none.db"))
        cm = self._manager_with_wallet("agent-1", ACCOUNT.address)

        result = asyncio.run(agent_stream.request_coins_handler(self._msg("agent-1", OTHER_ACCOUNT.address), cm, MagicMock()))
        assert result["action"] == "coin_request_failed"
        assert result["error"] == "wallet_mismatch"

    def test_enforce_unauthenticated_connection_rejected(self, monkeypatch, tmp_path):
        """No authenticated wallet on the connection → cannot name an address."""
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "none.db"))
        cm = self._manager_with_wallet("agent-1", None)

        result = asyncio.run(agent_stream.request_coins_handler(self._msg("agent-1", ACCOUNT.address), cm, MagicMock()))
        assert result["action"] == "coin_request_failed"
        assert result["error"] == "wallet_mismatch"

    def test_advisory_mismatch_allowed(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "none.db"))
        monkeypatch.setattr(agent_stream, "_record_coin_request", lambda *a, **k: None)
        monkeypatch.setattr(
            agent_stream, "_submit_transaction", lambda tx: {"success": True, "transaction_hash": "0x" + "ff" * 32}
        )
        fake_tx = MagicMock()
        fake_tx.generate_signed_transaction = MagicMock(return_value={"signed": True})
        monkeypatch.setattr(agent_stream, "TransactionService", lambda: fake_tx)

        cm = self._manager_with_wallet("agent-1", ACCOUNT.address)

        result = asyncio.run(agent_stream.request_coins_handler(self._msg("agent-1", OTHER_ACCOUNT.address), cm, MagicMock()))
        assert result["action"] == "coins_transferred"

    def test_disabled_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "none.db"))
        monkeypatch.setattr(agent_stream, "_record_coin_request", lambda *a, **k: None)
        monkeypatch.setattr(
            agent_stream, "_submit_transaction", lambda tx: {"success": True, "transaction_hash": "0x" + "ff" * 32}
        )
        fake_tx = MagicMock()
        fake_tx.generate_signed_transaction = MagicMock(return_value={"signed": True})
        monkeypatch.setattr(agent_stream, "TransactionService", lambda: fake_tx)

        cm = self._manager_with_wallet("agent-1", ACCOUNT.address)

        result = asyncio.run(agent_stream.request_coins_handler(self._msg("agent-1", OTHER_ACCOUNT.address), cm, MagicMock()))
        assert result["action"] == "coins_transferred"
