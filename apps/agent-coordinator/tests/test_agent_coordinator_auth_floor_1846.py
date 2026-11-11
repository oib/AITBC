"""#1846: agent-coordinator auth floor — authentication is mode-independent.

R11 audit F1 (verified on main): ``agent_msg_signature_mode`` defaulted to
``advisory``, and every ``authorize_*`` gate logged-and-allowed anonymous
callers — mutating, admin and message routes were reachable with no
credential at all. Pins:

* in-code default is ``enforce`` (env opt-down remains for migration);
* ``advisory`` AND ``enforce`` reject anonymous callers on scoped, any-
  principal and admin routes (401), while ``disabled`` stays open;
* advisory still allows scope *mismatches* for authenticated principals
  (the telemetry mode keeps its purpose);
* key registration can no longer silently overwrite an existing agent's
  key — admin or the bound agent only.
"""

from __future__ import annotations

import base64

import pytest

from agent_app.config import settings
from agent_app.encryption import public_keys

from tests import test_phase_c_auth as _tpc  # noqa: F401  (helpers/fixtures reused)
from tests.test_phase_c_auth import (  # noqa: F401
    ACCOUNT,
    OTHER_ACCOUNT,
    _admin_headers,
    _register_bound,
    _signed_headers,
)


@pytest.fixture
def registry():
    return _tpc.registry.__wrapped__()


@pytest.fixture
def fake_state(registry):
    return _tpc.fake_state.__wrapped__(registry)


@pytest.fixture
def client(monkeypatch, fake_state):
    return _tpc.client.__wrapped__(monkeypatch, fake_state)


@pytest.fixture(autouse=True)
def _clear_key_registry():
    public_keys.PUBLIC_KEY_REGISTRY.clear()
    yield
    public_keys.PUBLIC_KEY_REGISTRY.clear()


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    from agent_app.services import nonce_store

    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


def _pubkey_b64() -> str:
    return base64.b64encode(b"\x00" * 32).decode()


class TestDefaultMode:
    def test_in_code_default_is_enforce(self):
        """The shipped default must be enforce — advisory was the hole."""
        import importlib

        import agent_app.config as cfg

        importlib.reload(cfg)
        assert cfg.settings.agent_msg_signature_mode == "enforce"


class TestAdvisoryAuthFloor:
    """Anonymous -> 401 in advisory on every gated surface; authenticated
    principals keep advisory's log-and-allow scope semantics."""

    @pytest.fixture
    def advisory(self, client, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        return client

    @pytest.mark.parametrize(
        "method,url,kwargs",
        [
            ("POST", "/api/v1/agent/messages/broadcast", {"json": {"message_type": "direct", "payload": {"a": 1}}}),
            ("POST", "/v1/tasks/escrow/expire-stale", {}),
            ("POST", "/v1/tasks/queues/high/clear", {}),
            ("GET", "/api/v1/agent/messages/inbox?agent_id=a1", {}),
            ("GET", "/api/v1/agent/messages/history", {}),
        ],
    )
    def test_advisory_anonymous_401(self, advisory, fake_state, method, url, kwargs):
        fake_state.payment_escrow = None
        resp = advisory.request(method, url, **kwargs)
        assert resp.status_code == 401, f"{method} {url}: {resp.status_code} {resp.text[:120]}"

    def test_advisory_authenticated_scope_mismatch_still_allowed(self, advisory, fake_state):
        """Advisory's remaining job: an authenticated agent acting outside
        its scope is logged, not rejected."""
        _register_bound(advisory, "agent-1", ACCOUNT)
        resp = advisory.get("/api/v1/agent/messages/inbox?agent_id=agent-2", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200

    def test_advisory_admin_route_accepts_operator_key(self, advisory, fake_state):
        fake_state.agent_registry.discover_agents = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value=[]
        )
        resp = advisory.get("/api/v1/agent/messages/registry/stats", headers=_admin_headers())
        assert resp.status_code == 200


class TestKeyRegistrationOverwrite:
    """#1846: PUBLIC_KEY_REGISTRY overwrites need admin or the bound agent."""

    @pytest.fixture
    def advisory(self, client, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "advisory")
        return client

    def _register_key(self, client, agent_id: str, headers: dict | None = None) -> object:
        return client.post(
            "/api/v1/agent/keys/register",
            json={"agent_id": agent_id, "public_key": _pubkey_b64(), "key_id": "k1"},
            headers=headers or {},
        )

    def test_first_registration_by_bound_agent_ok(self, advisory):
        _register_bound(advisory, "agent-1", ACCOUNT)
        resp = self._register_key(advisory, "agent-1", _signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200, resp.text

    def test_overwrite_by_other_agent_403(self, advisory):
        _register_bound(advisory, "agent-1", ACCOUNT)
        _register_bound(advisory, "agent-2", OTHER_ACCOUNT)
        assert self._register_key(advisory, "agent-1", _signed_headers("agent-1", ACCOUNT)).status_code == 200
        resp = self._register_key(advisory, "agent-1", _signed_headers("agent-2", OTHER_ACCOUNT))
        assert resp.status_code == 403
        assert resp.json()["detail"] == "key_rotation_requires_admin_or_bound_agent"

    def test_overwrite_by_admin_ok(self, advisory):
        _register_bound(advisory, "agent-1", ACCOUNT)
        assert self._register_key(advisory, "agent-1", _signed_headers("agent-1", ACCOUNT)).status_code == 200
        resp = self._register_key(advisory, "agent-1", _admin_headers())
        assert resp.status_code == 200, resp.text

    def test_overwrite_anonymous_401(self, advisory):
        _register_bound(advisory, "agent-1", ACCOUNT)
        assert self._register_key(advisory, "agent-1", _signed_headers("agent-1", ACCOUNT)).status_code == 200
        resp = self._register_key(advisory, "agent-1")
        assert resp.status_code == 401

    def test_disabled_mode_unrestricted(self, client, monkeypatch):
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        assert self._register_key(client, "agent-1").status_code == 200
        assert self._register_key(client, "agent-1").status_code == 200  # overwrite allowed when disabled
