"""Phase A tests for agent-signed envelopes and registry identity binding.

Covers docs/agent-coordinator/agent-signed-envelopes.md §3–§6:

* envelope sign/verify round-trip and tamper detection,
* registration attestation accept/reject,
* re-registration hijack blocked (409) while the bound key can re-register,
* unsigned registration still working in advisory mode,
* ``signature_status`` stamped on stored records in advisory mode and
  enforced rejects in enforce mode.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)
os.environ["AITBC_ENABLE_RATE_LIMITING"] = "false"

pytest.importorskip("eth_account", reason="envelope signing tests need eth-account")
pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from eth_account import Account  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app.routers import agents as agents_router  # noqa: E402
from agent_app.routers import messages as messages_router  # noqa: E402
from agent_app.routing.agent_discovery import AgentRegistry  # noqa: E402
from agent_app.services import nonce_store  # noqa: E402

from aitbc.crypto.agent_envelope import (  # noqa: E402
    AGENT_MSG_SIGNATURE_VERSION,
    identity_claim,
    recover_agent_envelope_signer,
    rotation_claim,
    sign_agent_envelope,
    sign_identity_claim,
    sign_rotation_claim,
    verify_agent_envelope,
)

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
OTHER_KEY = "0x" + "43" * 32
OTHER_ACCOUNT = Account.from_key(OTHER_KEY)
CHAIN_ID = "ait-test-chain"


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


def _signed_send_fields(account, **overrides) -> dict:
    """A complete /send request whose ``signature`` covers every other field."""
    req: dict = {
        "sender": "agent-sender",
        "recipient": "agent-recipient",
        "content": {"text": "signed hello"},
        "message_type": "direct",
        "encrypt": False,
        "priority": "normal",
        "ttl": 300,
        "message_id": None,
        "signer": account.address,
        "signature_version": AGENT_MSG_SIGNATURE_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
        "nonce": "test-nonce-1",
    }
    req.update(overrides)
    req["signature"] = sign_agent_envelope(req, account.key.hex())
    return req


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    """Nonce state is process-global; each test starts with an empty map."""
    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


@pytest.fixture
def registry():
    """A real AgentRegistry (no Redis) so identity binding is genuinely stored."""
    return AgentRegistry()


@pytest.fixture
def agents_client(monkeypatch, registry):
    app = FastAPI()
    app.include_router(agents_router.router, prefix="/v1")
    monkeypatch.setattr(agents_router, "state", MagicMock(agent_registry=registry))
    return TestClient(app)


@pytest.fixture
def fake_storage():
    storage = MagicMock()
    storage.store_message = AsyncMock(return_value=True)
    storage.get_message = AsyncMock(return_value=None)
    storage.update_message_status = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def fake_connection_manager():
    cm = MagicMock()
    cm.send_personal_message = AsyncMock(return_value=True)
    return cm


def _issue_nonce(client: TestClient, agent_id: str) -> str:
    resp = client.get(f"/v1/agents/nonce?agent_id={agent_id}")
    assert resp.status_code == 200
    return resp.json()["nonce"]


# --------------------------------------------------------------------------- #
# Envelope helpers
# --------------------------------------------------------------------------- #


class TestEnvelopeHelpers:
    def test_envelope_signing_round_trip(self):
        payload = _signed_send_fields(ACCOUNT)
        signature = payload.pop("signature")

        assert verify_agent_envelope(payload, signature, ACCOUNT.address) is True
        assert recover_agent_envelope_signer(payload, signature) == ACCOUNT.address

    def test_agent_message_signing_payload_round_trip(self):
        from agent_app.protocols.communication import AgentMessage

        message = AgentMessage(sender_id="a", receiver_id="b")
        payload = message.signing_payload()
        assert "signature" not in payload
        signature = sign_agent_envelope(payload, PRIVATE_KEY)
        assert verify_agent_envelope(payload, signature, ACCOUNT.address) is True

    def test_invalid_signature_detected(self):
        payload = _signed_send_fields(ACCOUNT)
        signature = payload.pop("signature")

        # Tampered payload fails against the original signature.
        tampered = dict(payload, content={"text": "forged"})
        assert verify_agent_envelope(tampered, signature, ACCOUNT.address) is False

        # A signature by a different key does not match the claimed signer.
        other_sig = sign_agent_envelope(payload, OTHER_KEY)
        assert verify_agent_envelope(payload, other_sig, ACCOUNT.address) is False
        assert recover_agent_envelope_signer(payload, other_sig) == OTHER_ACCOUNT.address

        # Garbage signatures fail closed.
        assert verify_agent_envelope(payload, "0xdeadbeef", ACCOUNT.address) is False
        assert verify_agent_envelope(payload, "", ACCOUNT.address) is False


# --------------------------------------------------------------------------- #
# Registration attestation + identity binding
# --------------------------------------------------------------------------- #


class TestRegistrationAttestation:
    def _register(self, client, agent_id: str, **extra):
        body = {"agent_id": agent_id, "agent_type": "worker", **extra}
        return client.post("/v1/agents/register", json=body)

    def test_attested_registration_binds_identity(self, agents_client, registry):
        nonce = _issue_nonce(agents_client, "agent-1")
        fields = _registration_fields("agent-1", ACCOUNT, nonce)

        resp = self._register(agents_client, "agent-1", **fields)

        assert resp.status_code == 200
        assert resp.json()["identity_address"] == ACCOUNT.address
        assert registry.agents["agent-1"].identity_address == ACCOUNT.address
        assert registry.agents["agent-1"].registered_proof == fields["identity_proof"]

    def test_attestation_signed_by_wrong_key_rejected(self, agents_client, registry):
        nonce = _issue_nonce(agents_client, "agent-2")
        fields = _registration_fields("agent-2", OTHER_ACCOUNT, nonce)
        # Claim identity is ACCOUNT's but signed by OTHER — rejected.
        fields["identity_address"] = ACCOUNT.address

        resp = self._register(agents_client, "agent-2", **fields)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "invalid_identity_proof"
        assert "agent-2" not in registry.agents

    def test_attestation_with_unknown_nonce_rejected(self, agents_client):
        fields = _registration_fields("agent-3", ACCOUNT, "nonce-not-issued")

        resp = self._register(agents_client, "agent-3", **fields)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "invalid_identity_nonce"

    def test_nonce_is_one_time(self, agents_client):
        nonce = _issue_nonce(agents_client, "agent-4")
        fields = _registration_fields("agent-4", ACCOUNT, nonce)
        assert self._register(agents_client, "agent-4", **fields).status_code == 200

        # Replaying the consumed nonce — even for the same agent with an
        # otherwise-valid claim — fails closed.
        resp = self._register(agents_client, "agent-4", **fields)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "invalid_identity_nonce"

    def test_reregister_hijack_blocked_409(self, agents_client, registry):
        nonce = _issue_nonce(agents_client, "agent-6")
        assert self._register(agents_client, "agent-6", **_registration_fields("agent-6", ACCOUNT, nonce)).status_code == 200

        # Attacker re-registers the same agent_id with THEIR key (valid proof,
        # fresh nonce) — must not rebind.
        nonce2 = _issue_nonce(agents_client, "agent-6")
        hijack = _registration_fields("agent-6", OTHER_ACCOUNT, nonce2)
        resp = self._register(agents_client, "agent-6", **hijack)
        assert resp.status_code == 409
        assert registry.agents["agent-6"].identity_address == ACCOUNT.address

        # A plain unsigned re-registration does not clear the binding either.
        resp = self._register(agents_client, "agent-6")
        assert resp.status_code == 409
        assert registry.agents["agent-6"].identity_address == ACCOUNT.address

    def test_bound_key_can_reregister(self, agents_client, registry):
        nonce = _issue_nonce(agents_client, "agent-7")
        assert self._register(agents_client, "agent-7", **_registration_fields("agent-7", ACCOUNT, nonce)).status_code == 200

        nonce2 = _issue_nonce(agents_client, "agent-7")
        resp = self._register(agents_client, "agent-7", **_registration_fields("agent-7", ACCOUNT, nonce2))
        assert resp.status_code == 200
        assert registry.agents["agent-7"].identity_address == ACCOUNT.address

    def test_unsigned_registration_allowed_in_advisory(self, agents_client, registry, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")

        resp = self._register(agents_client, "agent-8")

        assert resp.status_code == 200
        assert resp.json()["identity_address"] is None
        assert registry.agents["agent-8"].identity_address is None

    def test_unsigned_registration_rejected_in_enforce(self, agents_client, monkeypatch):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")

        resp = self._register(agents_client, "agent-9")

        assert resp.status_code == 403
        assert "identity" in resp.json()["detail"]

    def test_identity_rotation_dual_proof(self, agents_client, registry):
        nonce = _issue_nonce(agents_client, "agent-10")
        assert self._register(agents_client, "agent-10", **_registration_fields("agent-10", ACCOUNT, nonce)).status_code == 200

        rotation_ts = datetime.now(UTC).isoformat()
        nonce2 = _issue_nonce(agents_client, "agent-10")
        registered_at = datetime.now(UTC).isoformat()
        new_claim = identity_claim(
            agent_id="agent-10",
            identity_address=OTHER_ACCOUNT.address,
            chain_id=CHAIN_ID,
            nonce=nonce2,
            registered_at=registered_at,
        )
        rot_claim = rotation_claim(
            agent_id="agent-10",
            old_address=ACCOUNT.address,
            new_address=OTHER_ACCOUNT.address,
            timestamp=rotation_ts,
        )
        resp = agents_client.put(
            "/v1/agents/agent-10/identity",
            json={
                "new_address": OTHER_ACCOUNT.address,
                "new_proof": sign_identity_claim(new_claim, OTHER_ACCOUNT.key.hex()),
                "rotation_proof": sign_rotation_claim(rot_claim, PRIVATE_KEY),
                "identity_nonce": nonce2,
                "registered_at": registered_at,
                "rotation_timestamp": rotation_ts,
                "chain_id": CHAIN_ID,
            },
        )

        assert resp.status_code == 200
        assert registry.agents["agent-10"].identity_address == OTHER_ACCOUNT.address

        # Without the currently bound key's rotation proof, rotating back is
        # refused — the new_proof is valid here so 403 can only come from the
        # rotation check.
        third_key = "0x" + "44" * 32
        nonce3 = _issue_nonce(agents_client, "agent-10")
        registered_at3 = datetime.now(UTC).isoformat()
        new_claim3 = identity_claim(
            agent_id="agent-10",
            identity_address=ACCOUNT.address,
            chain_id=CHAIN_ID,
            nonce=nonce3,
            registered_at=registered_at3,
        )
        rot_claim3 = rotation_claim(
            agent_id="agent-10",
            old_address=OTHER_ACCOUNT.address,
            new_address=ACCOUNT.address,
            timestamp=datetime.now(UTC).isoformat(),
        )
        resp = agents_client.put(
            "/v1/agents/agent-10/identity",
            json={
                "new_address": ACCOUNT.address,
                "new_proof": sign_identity_claim(new_claim3, PRIVATE_KEY),
                "rotation_proof": sign_rotation_claim(rot_claim3, third_key),  # not the bound key
                "identity_nonce": nonce3,
                "registered_at": registered_at3,
                "rotation_timestamp": rot_claim3["timestamp"],
                "chain_id": CHAIN_ID,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "invalid_rotation_proof"
        assert registry.agents["agent-10"].identity_address == OTHER_ACCOUNT.address


# --------------------------------------------------------------------------- #
# Advisory / enforce verification on POST /send
# --------------------------------------------------------------------------- #


class TestSendSignatureVerification:
    def _register_sender(self, client, registry, agent_id="agent-sender"):
        nonce = _issue_nonce(client, agent_id)
        fields = _registration_fields(agent_id, ACCOUNT, nonce)
        resp = client.post("/v1/agents/register", json={"agent_id": agent_id, "agent_type": "worker", **fields})
        assert resp.status_code == 200
        assert registry.agents[agent_id].identity_address == ACCOUNT.address

    def _app(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        """One TestClient serving both the agents and messages routers."""
        app = FastAPI()
        app.include_router(agents_router.router, prefix="/v1")
        app.include_router(messages_router.router)
        monkeypatch.setattr(
            messages_router,
            "state",
            MagicMock(message_storage=fake_storage, agent_registry=registry),
        )
        monkeypatch.setattr(
            agents_router,
            "state",
            MagicMock(agent_registry=registry),
        )
        monkeypatch.setattr(messages_router, "get_connection_manager", lambda: fake_connection_manager)
        return TestClient(app)

    def test_signed_message_stamped_verified(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)
        self._register_sender(client, registry)

        resp = client.post("/api/v1/agent/messages/send", json=_signed_send_fields(ACCOUNT))

        assert resp.status_code == 200
        assert resp.json()["signature_status"] == "verified"
        stored = fake_storage.store_message.call_args[0][1]
        assert stored["signature_status"] == "verified"
        assert stored["signer"] == ACCOUNT.address
        assert stored["signature"].startswith("0x")
        assert stored["signature_version"] == AGENT_MSG_SIGNATURE_VERSION

    def test_spoofed_sender_stamped_invalid_not_rejected_in_advisory(
        self, monkeypatch, registry, fake_storage, fake_connection_manager
    ):
        """Signed by a key that is NOT the sender's bound identity."""
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)
        self._register_sender(client, registry)

        req = _signed_send_fields(OTHER_ACCOUNT)  # valid sig, wrong identity
        resp = client.post("/api/v1/agent/messages/send", json=req)

        assert resp.status_code == 200
        assert resp.json()["signature_status"] == "invalid"
        stored = fake_storage.store_message.call_args[0][1]
        assert stored["signature_status"] == "invalid"

    def test_unsigned_message_stamped_unsigned(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)

        resp = client.post(
            "/api/v1/agent/messages/send",
            json={"sender": "agent-sender", "recipient": "agent-recipient", "content": {"text": "hi"}, "encrypt": False},
        )

        assert resp.status_code == 200
        assert resp.json()["signature_status"] == "unsigned"
        stored = fake_storage.store_message.call_args[0][1]
        assert stored["signature_status"] == "unsigned"

    def test_enforce_rejects_invalid_signature(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)
        self._register_sender(client, registry)

        req = _signed_send_fields(OTHER_ACCOUNT)
        resp = client.post("/api/v1/agent/messages/send", json=req)

        assert resp.status_code == 403
        fake_storage.store_message.assert_not_called()

    def test_enforce_rejects_unsigned(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)

        resp = client.post(
            "/api/v1/agent/messages/send",
            json={"sender": "agent-sender", "recipient": "agent-recipient", "content": {"text": "hi"}, "encrypt": False},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "missing_signature"
        fake_storage.store_message.assert_not_called()

    def test_disabled_mode_verifies_nothing(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        """Default mode: unsigned sends flow through with no stamp at all."""
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)

        resp = client.post(
            "/api/v1/agent/messages/send",
            json={"sender": "agent-sender", "recipient": "agent-recipient", "content": {"text": "hi"}, "encrypt": False},
        )

        assert resp.status_code == 200
        assert resp.json()["signature_status"] is None
        stored = fake_storage.store_message.call_args[0][1]
        assert "signature_status" not in stored

    def test_stale_timestamp_rejected_in_enforce(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)
        self._register_sender(client, registry)

        req = _signed_send_fields(ACCOUNT, timestamp="2020-01-01T00:00:00+00:00")
        resp = client.post("/api/v1/agent/messages/send", json=req)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "stale_timestamp"

    def test_nonce_replay_rejected_in_enforce(self, monkeypatch, registry, fake_storage, fake_connection_manager):
        from agent_app.config import settings

        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        client = self._app(monkeypatch, registry, fake_storage, fake_connection_manager)
        self._register_sender(client, registry)

        req = _signed_send_fields(ACCOUNT, message_id="msg-fixed-1", nonce="nonce-once")
        assert client.post("/api/v1/agent/messages/send", json=req).status_code == 200

        # Same sender+nonce inside the TTL → replay.
        req2 = _signed_send_fields(ACCOUNT, message_id="msg-fixed-2", nonce="nonce-once")
        resp = client.post("/api/v1/agent/messages/send", json=req2)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "nonce_replayed"
