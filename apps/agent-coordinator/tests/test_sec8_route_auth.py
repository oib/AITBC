"""SEC-8: auth coverage for consensus.py and ai.py routes + /health detail.

Every mutating route on the two routers must reject anonymous callers
(401) and non-admin principals (403) in ``enforce`` mode, and succeed for
the operator key. Read/statistics routes require any resolved principal.
``/health`` stays 200 for everyone but returns detail fields only to a
resolved principal. A route-inventory test fails if a new
POST/PUT/DELETE route is added to either router without an auth
dependency.
"""

from __future__ import annotations

import os
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
from agent_app.routers import agents as agents_router  # noqa: E402
from agent_app.routers import agent_auth as agent_auth_router  # noqa: E402
from agent_app.routers import ai as ai_router  # noqa: E402
from agent_app.routers import consensus as consensus_router  # noqa: E402
from agent_app.routers import health as health_router  # noqa: E402
from agent_app.routers import keys as keys_router  # noqa: E402
from agent_app.routing.agent_discovery import AgentRegistry  # noqa: E402
from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402
from agent_app.services import nonce_store  # noqa: E402

from aitbc.crypto.agent_envelope import (  # noqa: E402
    identity_claim,
    request_claim,
    sign_identity_claim,
    sign_request_claim,
)

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
CHAIN_ID = "ait-test-chain"
OPERATOR_KEY = "test-operator-key"


# Routes that must reject anonymous callers entirely in enforce mode.
# (method, url, kwargs) — urls carry concrete path params.
ADMIN_CALLS = [
    ("POST", "/v1/consensus/node/register", {"json": {"node_id": "n1"}}),
    ("POST", "/v1/consensus/proposal/create", {"json": {"title": "t"}}),
    ("POST", "/v1/consensus/proposal/p1/vote?node_id=n1&vote=true", {}),
    ("PUT", "/v1/consensus/algorithm?algorithm=pbft", {}),
    ("PUT", "/v1/consensus/node/n1/status?is_active=true", {}),
    ("POST", "/v1/ai/learning/experience", {"json": {"a": 1}}),
    ("POST", "/v1/ai/neural-network/create", {"json": {"layers": [1]}}),
    ("POST", "/v1/ai/neural-network/net-1/train", {"json": [{"x": 1}]}),
    ("POST", "/v1/ai/ml-model/create", {"json": {"type": "x"}}),
    ("POST", "/v1/ai/ml-model/m1/train", {"json": [{"x": 1}]}),
]

ANY_PRINCIPAL_CALLS = [
    ("GET", "/v1/consensus/statistics", {}),
    ("GET", "/v1/consensus/proposal/p1", {}),
    ("GET", "/v1/advanced-features/status", {}),
    ("GET", "/v1/ai/statistics", {}),
    ("GET", "/v1/ai/learning/statistics", {}),
    ("POST", "/v1/ai/learning/predict?action=a", {"json": {}}),
    ("POST", "/v1/ai/learning/recommend", {"json": {"context": {}, "available_actions": ["a"]}}),
    ("POST", "/v1/ai/neural-network/net-1/predict", {"json": [1.0]}),
    ("POST", "/v1/ai/ml-model/m1/predict", {"json": [1.0]}),
]


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


@pytest.fixture
def fake_state():
    state = MagicMock()
    state.agent_registry = AgentRegistry()
    return state


@pytest.fixture
def client(monkeypatch, fake_state):
    monkeypatch.setenv("COORDINATOR_API_KEY", OPERATOR_KEY)
    consensus_stub = MagicMock()
    consensus_stub.register_node = AsyncMock(return_value={"ok": True})
    consensus_stub.create_proposal = AsyncMock(return_value={"ok": True})
    consensus_stub.cast_vote = AsyncMock(return_value={"ok": True})
    consensus_stub.get_proposal_status = AsyncMock(return_value={"status": "open"})
    consensus_stub.set_consensus_algorithm = AsyncMock(return_value={"ok": True})
    consensus_stub.get_consensus_statistics = AsyncMock(return_value={"total_proposals": 0})
    consensus_stub.update_node_status = AsyncMock(return_value={"ok": True})
    ai_stub = MagicMock()
    ai_stub.create_neural_network = AsyncMock(return_value={"id": "net-1"})
    ai_stub.train_neural_network = AsyncMock(return_value={"ok": True})
    ai_stub.predict_with_neural_network = AsyncMock(return_value={"prediction": [0.5]})
    ai_stub.create_ml_model = AsyncMock(return_value={"id": "m1"})
    ai_stub.train_ml_model = AsyncMock(return_value={"ok": True})
    ai_stub.predict_with_ml_model = AsyncMock(return_value={"prediction": [0.5]})
    ai_stub.get_ai_statistics = AsyncMock(return_value={"models": 0})
    learning_stub = MagicMock()
    learning_stub.record_experience = AsyncMock(return_value={"ok": True})
    learning_stub.get_learning_statistics = AsyncMock(return_value={"experiences": 0})
    learning_stub.predict_performance = AsyncMock(return_value={"score": 0.5})
    learning_stub.recommend_action = AsyncMock(return_value={"action": "a"})
    for mod in (consensus_router,):
        monkeypatch.setattr(mod, "distributed_consensus", consensus_stub)
        monkeypatch.setattr(mod, "ai_integration", ai_stub)
        monkeypatch.setattr(mod, "learning_system", learning_stub)
    for mod in (ai_router,):
        monkeypatch.setattr(mod, "ai_integration", ai_stub)
        monkeypatch.setattr(mod, "learning_system", learning_stub)

    app = FastAPI()
    app.include_router(agents_router.router, prefix="/v1")
    app.include_router(agent_auth_router.router)
    app.include_router(keys_router.router)
    app.include_router(consensus_router.router, prefix="/v1")
    app.include_router(ai_router.router, prefix="/v1")
    app.include_router(health_router.router)
    for module in (agents_router, agent_auth_router, agent_auth_svc):
        monkeypatch.setattr(module, "state", fake_state)
    return TestClient(app)


@pytest.fixture
def enforce(client, monkeypatch):
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
    return client


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
    assert resp.status_code == 200
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


def _admin_headers() -> dict[str, str]:
    return {"X-Api-Key": OPERATOR_KEY}


def _call(client: TestClient, method: str, url: str, kwargs: dict, headers: dict | None = None):
    return client.request(method, url, headers=headers or {}, **kwargs)


class TestConsensusAdminGates:
    """The five mutating consensus routes: 401 anonymous, 403 agent, 200 operator."""

    @pytest.mark.parametrize("method,url,kwargs", ADMIN_CALLS)
    def test_anonymous_401(self, enforce, method, url, kwargs):
        resp = _call(enforce, method, url, kwargs)
        assert resp.status_code == 401, f"{method} {url}: {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", ADMIN_CALLS)
    def test_agent_principal_403(self, enforce, method, url, kwargs):
        _register_bound(enforce, "agent-1", ACCOUNT)
        resp = _call(enforce, method, url, kwargs, headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 403, f"{method} {url}: {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", ADMIN_CALLS)
    def test_operator_ok(self, enforce, method, url, kwargs):
        resp = _call(enforce, method, url, kwargs, headers=_admin_headers())
        assert resp.status_code == 200, f"{method} {url}: {resp.text}"


class TestReadGates:
    """Statistics/status reads and predict/recommend: 401 anonymous, 200 agent."""

    @pytest.mark.parametrize("method,url,kwargs", ANY_PRINCIPAL_CALLS)
    def test_anonymous_401(self, enforce, method, url, kwargs):
        resp = _call(enforce, method, url, kwargs)
        assert resp.status_code == 401, f"{method} {url}: {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", ANY_PRINCIPAL_CALLS)
    def test_agent_principal_ok(self, enforce, method, url, kwargs):
        _register_bound(enforce, "agent-1", ACCOUNT)
        resp = _call(enforce, method, url, kwargs, headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200, f"{method} {url}: {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", ANY_PRINCIPAL_CALLS)
    def test_operator_ok(self, enforce, method, url, kwargs):
        resp = _call(enforce, method, url, kwargs, headers=_admin_headers())
        assert resp.status_code == 200, f"{method} {url}: {resp.text}"


class TestHealthDetailGating:
    def test_anonymous_gets_status_only(self, enforce):
        resp = enforce.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body and "service" in body
        assert "details" not in body and "version" not in body

    def test_principal_gets_full_detail(self, enforce):
        _register_bound(enforce, "agent-1", ACCOUNT)
        resp = enforce.get("/health", headers=_signed_headers("agent-1", ACCOUNT))
        assert resp.status_code == 200
        body = resp.json()
        assert "version" in body and "details" in body

    def test_operator_gets_full_detail(self, enforce):
        resp = enforce.get("/health", headers=_admin_headers())
        assert resp.status_code == 200
        assert "version" in resp.json()


class TestRouteInventory:
    """A new POST/PUT/DELETE/PATCH route on these routers must carry an
    auth dependency — this test fails the commit if one appears without
    a ``principal`` parameter."""

    @pytest.mark.parametrize("mod", [consensus_router, ai_router])
    def test_mutating_routes_have_principal(self, mod):
        import inspect

        missing = []
        for route in mod.router.routes:
            methods = getattr(route, "methods", set()) or set()
            if not methods & {"POST", "PUT", "DELETE", "PATCH"}:
                continue
            params = inspect.signature(route.endpoint).parameters
            if "principal" not in params:
                missing.append(f"{sorted(methods)} {route.path}")
        assert not missing, f"mutating routes without auth dependency: {missing}"
