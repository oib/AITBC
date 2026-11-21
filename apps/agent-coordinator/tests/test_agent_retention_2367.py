"""#2367 — durable read credential for reaped agents.

``_cleanup_inactive_agents`` used to ``unregister_agent`` an INACTIVE agent
one hour after its last heartbeat, which deleted the registry record — and
with it the ``identity_address`` binding — so every signed ``X-Agent-*`` read
401'd ``agent_not_bound`` forever. The registry now retains INACTIVE records
for ``agent_registry_retention_seconds`` (default 7d): the binding keeps
resolving for reads, while discovery/task assignment still require ACTIVE
and a heartbeat revives the agent. Past the window the record is unregistered
as before.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("eth_account", reason="signed-header tests need eth-account")
pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from eth_account import Account  # noqa: E402

from agent_app import state as app_state  # noqa: E402
from agent_app.routing.agent_discovery import (  # noqa: E402
    AgentRegistry,
    AgentStatus,
    create_agent_info,
)
from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402
from agent_app.services import nonce_store  # noqa: E402

from aitbc.crypto.agent_envelope import request_claim, sign_request_claim  # noqa: E402

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
AGENT_ID = "agent-retained"


@pytest.fixture(autouse=True)
def _clear_nonce_store():
    nonce_store.get_nonce_store()._memory.clear()
    yield
    nonce_store.get_nonce_store()._memory.clear()


@pytest.fixture
def registry():
    return AgentRegistry()


async def _register_inactive(registry: AgentRegistry, agent_id: str = AGENT_ID, inactive_age: timedelta | None = None) -> None:
    """Register a bound agent and park it INACTIVE with a backdated heartbeat."""
    agent = create_agent_info(
        agent_id=agent_id,
        agent_type="worker",
        capabilities=["compute"],
        services=[],
        endpoints={},
        identity_address=ACCOUNT.address,
        registered_proof="0xregistered-proof",
    )
    agent.status = AgentStatus.INACTIVE
    if inactive_age is not None:
        agent.last_heartbeat = datetime.now(UTC) - inactive_age
    assert await registry.register_agent(agent) is True


def _signed_headers(agent_id: str, account=ACCOUNT) -> dict[str, str]:
    ts = datetime.now(UTC).isoformat()
    nc = uuid4().hex
    claim = request_claim(agent_id=agent_id, timestamp=ts, nonce=nc)
    return {
        "X-Agent-Id": agent_id,
        "X-Agent-Signature": sign_request_claim(claim, account.key.hex()),
        "X-Agent-Timestamp": ts,
        "X-Agent-Nonce": nc,
    }


def _request(headers: dict[str, str]):
    return SimpleNamespace(headers=headers)


class TestRetainedAgentReadAuth:
    async def test_inactive_agent_signed_headers_still_resolve(self, registry, monkeypatch):
        """A reaped-but-retained agent keeps its read credential (#2367a)."""
        await _register_inactive(registry, inactive_age=timedelta(hours=2))
        monkeypatch.setattr(app_state, "agent_registry", registry)

        principal = await agent_auth_svc.signed_headers_principal(_request(_signed_headers(AGENT_ID)))

        assert principal is not None
        assert principal.agent_id == AGENT_ID
        assert principal.wallet == ACCOUNT.address
        assert principal.auth_type == "signed_headers"

    async def test_unregistered_agent_signed_headers_still_rejected(self, registry, monkeypatch):
        """Retention is not a skeleton key: no record, no principal."""
        monkeypatch.setattr(app_state, "agent_registry", registry)

        principal = await agent_auth_svc.signed_headers_principal(_request(_signed_headers("ghost")))

        assert principal is None


class TestRetainedAgentDiscovery:
    async def test_inactive_agent_excluded_from_unfiltered_discovery(self, registry):
        await _register_inactive(registry)
        await registry.register_agent(
            create_agent_info(
                agent_id="agent-live",
                agent_type="worker",
                capabilities=["compute"],
                services=[],
                endpoints={},
            )
        )

        found = await registry.discover_agents({})
        ids = {a.agent_id for a in found}

        assert AGENT_ID not in ids
        assert "agent-live" in ids

    async def test_inactive_agent_excluded_from_active_assignment_query(self, registry):
        """The load balancer's ``{"status": ACTIVE}`` query never sees it (#2367c)."""
        await _register_inactive(registry)

        found = await registry.discover_agents({"status": AgentStatus.ACTIVE})

        assert all(a.agent_id != AGENT_ID for a in found)

    async def test_explicit_inactive_status_query_still_returns_it(self, registry):
        """Ops inspection can still ask for inactive agents by name."""
        await _register_inactive(registry)

        found = await registry.discover_agents({"status": "inactive"})

        assert [a.agent_id for a in found] == [AGENT_ID]

    async def test_heartbeat_revives_retained_agent_into_discovery(self, registry):
        """A retained agent that comes back is assignable work again."""
        await _register_inactive(registry)

        assert await registry.update_agent_status(AGENT_ID, AgentStatus.ACTIVE, {}) is True

        found = await registry.discover_agents({"status": AgentStatus.ACTIVE})
        assert AGENT_ID in {a.agent_id for a in found}


class TestRetentionExpiry:
    async def test_expired_retention_unregisters_agent(self):
        registry = AgentRegistry(retention_seconds=3600)
        await _register_inactive(registry, inactive_age=timedelta(hours=2))

        await registry._retire_expired_agents()

        assert registry.get_agent_by_id(AGENT_ID) is None

    async def test_within_retention_agent_is_kept(self):
        registry = AgentRegistry(retention_seconds=3600)
        await _register_inactive(registry, inactive_age=timedelta(minutes=30))

        await registry._retire_expired_agents()

        agent = registry.get_agent_by_id(AGENT_ID)
        assert agent is not None
        assert agent.status == AgentStatus.INACTIVE

    async def test_active_agent_never_reaped_by_retention(self):
        registry = AgentRegistry(retention_seconds=3600)
        agent = create_agent_info(
            agent_id="agent-busy",
            agent_type="worker",
            capabilities=[],
            services=[],
            endpoints={},
        )
        agent.last_heartbeat = datetime.now(UTC) - timedelta(days=30)
        assert await registry.register_agent(agent) is True

        await registry._retire_expired_agents()

        # ACTIVE records are the heartbeat monitor's job, not the reaper's.
        assert registry.get_agent_by_id("agent-busy") is not None
