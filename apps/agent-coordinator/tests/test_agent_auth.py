"""Phase B1 tests — coordinator-side agent session auth and principal binding.

Covers:

* ``POST /api/v1/agent/auth/nonce`` + ``/login`` — wallet-login nonce → signed
  login claim → JWT round-trip; wrong-wallet, unregistered, unbound and
  nonce-replay rejections.
* The ``X-Agent-*`` signed-request headers resolved by
  ``services/agent_auth.optional_agent`` — accept, bad-signature reject,
  unbound-agent reject and nonce replay.
* WebSocket principal binding — ``?token=`` resolves to a principal and, in
  enforce mode, a mismatched ``agent_id`` is refused; advisory logs and
  allows; the shared key binds to ``hub-coordinator`` only.
* Inbox/history authorization — enforce mode requires a principal and scopes
  it to its own agent_id; admin principals bypass; advisory/disabled are
  unchanged.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)
os.environ["AITBC_ENABLE_RATE_LIMITING"] = "false"

pytest.importorskip("eth_account", reason="wallet-login tests need eth-account")
pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from eth_account import Account  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from agent_app import state as app_state  # noqa: E402
from agent_app.routers import agent_auth as agent_auth_router  # noqa: E402
from agent_app.routers import agents as agents_router  # noqa: E402
from agent_app.routers import messages as messages_router  # noqa: E402
from agent_app.routers import websocket as websocket_router  # noqa: E402
from agent_app.routing.agent_discovery import AgentRegistry  # noqa: E402
from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402
from agent_app.services import nonce_store  # noqa: E402

from aitbc.auth.jwt import create_access_token, get_jwt_handler  # noqa: E402
from aitbc.crypto.agent_envelope import (  # noqa: E402
    identity_claim,
    login_claim,
    request_claim,
    sign_identity_claim,
    sign_login_claim,
    sign_request_claim,
)

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
    """identity_* fields for POST /v1/agents/register, signed by ``account``."""
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


def _signed_headers(agent_id: str, account, nonce: str | None = None, timestamp: str | None = None) -> dict[str, str]:
    """A valid X-Agent-* header set signed by ``account``."""
    ts = timestamp or datetime.now(UTC).isoformat()
    nc = nonce or uuid4().hex
    claim = request_claim(agent_id=agent_id, timestamp=ts, nonce=nc)
    return {
        "X-Agent-Id": agent_id,
        "X-Agent-Timestamp": ts,
        "X-Agent-Nonce": nc,
        "X-Agent-Signature": sign_request_claim(claim, account.key.hex()),
    }


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def fake_storage():
    storage = MagicMock()
    storage.store_message = AsyncMock(return_value=True)
    storage.get_message = AsyncMock(return_value=None)
    storage.update_message_status = AsyncMock(return_value=True)
    storage.get_messages_by_receiver = AsyncMock(return_value=[])
    storage.get_messages_by_sender = AsyncMock(return_value=[])
    storage.get_all_messages = AsyncMock(return_value=[])
    storage.get_message_count = AsyncMock(return_value=0)
    storage.add_subscription = AsyncMock(return_value=True)
    storage.remove_subscription = AsyncMock(return_value=True)
    storage.get_subscriptions = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def client(monkeypatch, registry, fake_storage):
    """One TestClient serving the agents, agent-auth, messages and ws routers."""
    monkeypatch.setenv("COORDINATOR_API_KEY", OPERATOR_KEY)
    app = FastAPI()
    app.include_router(agents_router.router, prefix="/v1")
    app.include_router(agent_auth_router.router)
    app.include_router(messages_router.router)
    app.include_router(websocket_router.router)
    fake_state = MagicMock(agent_registry=registry, message_storage=fake_storage)
    for module in (agents_router, agent_auth_router, messages_router, agent_auth_svc):
        monkeypatch.setattr(module, "state", fake_state)
    return TestClient(app)


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


def _register_unbound(client: TestClient, agent_id: str) -> None:
    resp = client.post("/v1/agents/register", json={"agent_id": agent_id, "agent_type": "worker"})
    assert resp.status_code == 200, resp.text


def _login_nonce(client: TestClient, agent_id: str) -> tuple[str, str]:
    resp = client.post(f"/api/v1/agent/auth/nonce?agent_id={agent_id}")
    assert resp.status_code == 200
    body = resp.json()
    return body["nonce"], body["chain_id"]


def _login(client: TestClient, agent_id: str, account) -> str:
    """Full nonce→claim→login round-trip; returns the access token."""
    nonce, chain_id = _login_nonce(client, agent_id)
    claim = login_claim(agent_id=agent_id, wallet_address=account.address, chain_id=chain_id, nonce=nonce)
    resp = client.post(
        "/api/v1/agent/auth/login",
        json={
            "agent_id": agent_id,
            "wallet_address": account.address,
            "nonce": nonce,
            "signature": sign_login_claim(claim, account.key.hex()),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# --------------------------------------------------------------------------- #
# Wallet login
# --------------------------------------------------------------------------- #


class TestAgentLogin:
    def test_nonce_login_jwt_round_trip(self, client):
        _register_bound(client, "agent-1", ACCOUNT)

        token = _login(client, "agent-1", ACCOUNT)

        validation = get_jwt_handler().validate_token(token)
        assert validation["valid"] is True
        payload = validation["payload"]
        assert payload["sub"] == "agent-1"
        assert payload["agent_id"] == "agent-1"
        assert payload["wallet"] == ACCOUNT.address
        assert payload["role"] == "agent"

    def test_login_nonce_is_one_time(self, client):
        _register_bound(client, "agent-1", ACCOUNT)
        nonce, chain_id = _login_nonce(client, "agent-1")
        claim = login_claim(agent_id="agent-1", wallet_address=ACCOUNT.address, chain_id=chain_id, nonce=nonce)
        body = {
            "agent_id": "agent-1",
            "wallet_address": ACCOUNT.address,
            "nonce": nonce,
            "signature": sign_login_claim(claim, PRIVATE_KEY),
        }
        assert client.post("/api/v1/agent/auth/login", json=body).status_code == 200

        resp = client.post("/api/v1/agent/auth/login", json=body)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "invalid_nonce"

    def test_wrong_wallet_rejected(self, client):
        """A valid signature from a key that is not the bound identity fails."""
        _register_bound(client, "agent-1", ACCOUNT)
        nonce, chain_id = _login_nonce(client, "agent-1")
        claim = login_claim(agent_id="agent-1", wallet_address=OTHER_ACCOUNT.address, chain_id=chain_id, nonce=nonce)
        resp = client.post(
            "/api/v1/agent/auth/login",
            json={
                "agent_id": "agent-1",
                "wallet_address": OTHER_ACCOUNT.address,
                "nonce": nonce,
                "signature": sign_login_claim(claim, OTHER_KEY),
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "wallet_mismatch"

    def test_signature_for_bound_wallet_but_wrong_claim_rejected(self, client):
        """Signature by the bound key over a *different* wallet claim fails."""
        _register_bound(client, "agent-1", ACCOUNT)
        nonce, chain_id = _login_nonce(client, "agent-1")
        # Sign a claim naming another wallet with the bound key, then present it.
        claim = login_claim(agent_id="agent-1", wallet_address=OTHER_ACCOUNT.address, chain_id=chain_id, nonce=nonce)
        resp = client.post(
            "/api/v1/agent/auth/login",
            json={
                "agent_id": "agent-1",
                "wallet_address": OTHER_ACCOUNT.address,
                "nonce": nonce,
                "signature": sign_login_claim(claim, PRIVATE_KEY),
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "wallet_mismatch"

    def test_unregistered_agent_rejected(self, client):
        nonce, chain_id = _login_nonce(client, "ghost")
        claim = login_claim(agent_id="ghost", wallet_address=ACCOUNT.address, chain_id=chain_id, nonce=nonce)
        resp = client.post(
            "/api/v1/agent/auth/login",
            json={
                "agent_id": "ghost",
                "wallet_address": ACCOUNT.address,
                "nonce": nonce,
                "signature": sign_login_claim(claim, PRIVATE_KEY),
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "agent_not_registered"

    def test_unbound_agent_rejected(self, client):
        """Registered without an identity binding cannot log in."""
        _register_unbound(client, "agent-plain")
        nonce, chain_id = _login_nonce(client, "agent-plain")
        claim = login_claim(agent_id="agent-plain", wallet_address=ACCOUNT.address, chain_id=chain_id, nonce=nonce)
        resp = client.post(
            "/api/v1/agent/auth/login",
            json={
                "agent_id": "agent-plain",
                "wallet_address": ACCOUNT.address,
                "nonce": nonce,
                "signature": sign_login_claim(claim, PRIVATE_KEY),
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "agent_not_bound"


# --------------------------------------------------------------------------- #
# Signed-request headers + session probe
# --------------------------------------------------------------------------- #


class TestSignedHeaderAuth:
    def test_signed_headers_accepted(self, client):
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/auth/session", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == "agent-1"
        assert body["wallet"] == ACCOUNT.address
        assert body["auth_type"] == "signed_headers"

    def test_bad_signature_rejected(self, client):
        _register_bound(client, "agent-1", ACCOUNT)
        headers = _signed_headers("agent-1", OTHER_ACCOUNT)  # valid sig, wrong key
        resp = client.get("/api/v1/agent/auth/session", headers=headers)
        assert resp.status_code == 401

    def test_unbound_agent_headers_rejected(self, client):
        _register_unbound(client, "agent-plain")
        resp = client.get("/api/v1/agent/auth/session", headers=_signed_headers("agent-plain", ACCOUNT))
        assert resp.status_code == 401

    def test_signed_headers_replay_rejected(self, client):
        _register_bound(client, "agent-1", ACCOUNT)
        headers = _signed_headers("agent-1", ACCOUNT, nonce="fixed-nonce")
        assert client.get("/api/v1/agent/auth/session", headers=headers).status_code == 200
        # Same header set replayed inside the skew window → nonce dedup fires.
        resp = client.get("/api/v1/agent/auth/session", headers=headers)
        assert resp.status_code == 401

    def test_stale_timestamp_rejected(self, client):
        _register_bound(client, "agent-1", ACCOUNT)
        headers = _signed_headers("agent-1", ACCOUNT, timestamp="2020-01-01T00:00:00+00:00")
        assert client.get("/api/v1/agent/auth/session", headers=headers).status_code == 401

    def test_agent_jwt_accepted(self, client):
        _register_bound(client, "agent-1", ACCOUNT)
        token = _login(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/auth/session", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent-1"
        assert resp.json()["auth_type"] == "jwt"

    def test_shared_key_is_operator_principal(self, client):
        resp = client.get("/api/v1/agent/auth/session", headers={"X-Api-Key": OPERATOR_KEY})
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == "hub-coordinator"
        assert body["is_admin"] is True


# --------------------------------------------------------------------------- #
# Inbox / history authorization (enforce)
# --------------------------------------------------------------------------- #


class TestInboxAuthorization:
    def test_enforce_requires_principal(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        resp = client.get("/api/v1/agent/messages/inbox?agent_id=agent-1")
        assert resp.status_code == 401

    def test_enforce_own_inbox_ok(self, client, fake_storage, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/messages/inbox?agent_id=agent-1", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200
        fake_storage.get_messages_by_receiver.assert_called_once_with("agent-1", 100, 0)

    def test_enforce_cross_agent_inbox_403(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/messages/inbox?agent_id=agent-2", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 403

    def test_enforce_cross_agent_inbox_via_jwt_403(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        token = _login(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/messages/inbox?agent_id=agent-2", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_advisory_mismatch_allowed(self, client, monkeypatch):
        """Advisory keeps the open read; the mismatch is only logged."""
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/messages/inbox?agent_id=agent-2", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200

    def test_disabled_open_read(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        resp = client.get("/api/v1/agent/messages/inbox?agent_id=agent-9")
        assert resp.status_code == 200

    def test_enforce_subscribe_cross_agent_403(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.post(
            "/api/v1/agent/messages/subscribe",
            json={"agent_id": "agent-2", "topic": "jobs"},
            headers=_signed_headers("agent-1", ACCOUNT),
        )
        assert resp.status_code == 403

    def test_enforce_mark_read_requires_receiver(self, client, fake_storage, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        fake_storage.get_message = AsyncMock(return_value={"sender": "agent-1", "recipient": "agent-2"})
        # agent-1 is the sender, not the receiver — cannot mark read.
        resp = client.post("/api/v1/agent/messages/id/msg-1/read", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 403
        fake_storage.update_message_status.assert_not_called()

    def test_enforce_receiver_can_mark_read(self, client, fake_storage, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-2", OTHER_ACCOUNT)
        fake_storage.get_message = AsyncMock(return_value={"sender": "agent-1", "recipient": "agent-2"})
        resp = client.post("/api/v1/agent/messages/id/msg-1/read", headers=_signed_headers("agent-2", OTHER_ACCOUNT))
        assert resp.status_code == 200
        fake_storage.update_message_status.assert_called_once_with("msg-1", "read")


class TestHistoryAuthorization:
    def test_enforce_unfiltered_history_scoped_to_principal(self, client, fake_storage, monkeypatch):
        """A non-admin principal never reaches get_all_messages in enforce."""
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        own = {"sender": "agent-1", "recipient": "agent-2", "timestamp": "2026-01-01T00:00:01+00:00"}
        fake_storage.get_messages_by_sender = AsyncMock(return_value=[own])
        fake_storage.get_messages_by_receiver = AsyncMock(return_value=[])

        resp = client.get("/api/v1/agent/messages/history", headers=_signed_headers("agent-1", ACCOUNT))

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        fake_storage.get_all_messages.assert_not_called()

    def test_enforce_history_filter_other_agent_403(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        resp = client.get("/api/v1/agent/messages/history?sender_id=agent-2", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 403

    def test_enforce_history_anonymous_401(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        assert client.get("/api/v1/agent/messages/history").status_code == 401

    def test_admin_bypass_full_history(self, client, fake_storage, monkeypatch):
        """An admin JWT sees the unfiltered history even in enforce mode."""
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        admin_token = create_access_token(user_id="admin_001", role="admin")
        resp = client.get("/api/v1/agent/messages/history", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        fake_storage.get_all_messages.assert_called_once()

    def test_advisory_unfiltered_history_unchanged(self, client, fake_storage, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        resp = client.get("/api/v1/agent/messages/history")
        assert resp.status_code == 200
        fake_storage.get_all_messages.assert_called_once()


# --------------------------------------------------------------------------- #
# WebSocket principal binding
# --------------------------------------------------------------------------- #


class TestWebSocketBinding:
    URL = "/api/v1/agent/messages/stream"

    def test_no_token_rejected(self, client):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{self.URL}?agent_id=agent-1"):
                pass

    def test_jwt_matching_agent_accepted(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        token = _login(client, "agent-1", ACCOUNT)
        with client.websocket_connect(f"{self.URL}?agent_id=agent-1&token={token}") as ws:
            assert ws.receive_json()["type"] == "connection_established"

    def test_jwt_mismatch_rejected_in_enforce(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        _register_bound(client, "agent-1", ACCOUNT)
        token = _login(client, "agent-1", ACCOUNT)
        with pytest.raises(WebSocketDisconnect) as raised:
            with client.websocket_connect(f"{self.URL}?agent_id=agent-2&token={token}"):
                pass
        assert raised.value.code == 1008

    def test_shared_key_binds_to_hub_coordinator(self, client, monkeypatch):
        """The operator key is the fixed identity hub-coordinator — enforce mode
        refuses it for any other agent_id."""
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        with client.websocket_connect(f"{self.URL}?agent_id=hub-coordinator&token={OPERATOR_KEY}") as ws:
            assert ws.receive_json()["type"] == "connection_established"
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{self.URL}?agent_id=agent-1&token={OPERATOR_KEY}"):
                pass

    def test_advisory_mismatch_allowed(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        _register_bound(client, "agent-1", ACCOUNT)
        token = _login(client, "agent-1", ACCOUNT)
        with client.websocket_connect(f"{self.URL}?agent_id=agent-2&token={token}") as ws:
            assert ws.receive_json()["type"] == "connection_established"

    def test_disabled_mismatch_allowed(self, client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        _register_bound(client, "agent-1", ACCOUNT)
        token = _login(client, "agent-1", ACCOUNT)
        with client.websocket_connect(f"{self.URL}?agent_id=agent-2&token={token}") as ws:
            assert ws.receive_json()["type"] == "connection_established"

    def test_ws_status_requires_principal(self, client):
        assert client.get("/api/v1/agent/ws/status").status_code == 401
        resp = client.get("/api/v1/agent/ws/status", headers={"X-Api-Key": OPERATOR_KEY})
        assert resp.status_code == 200
        assert resp.json()["authenticated_as"] == "hub-coordinator"


def test_state_module_uses_real_registry():
    """Sanity: the app-state module exists and is patchable (fixture wiring)."""
    assert hasattr(app_state, "agent_registry")
