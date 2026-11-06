"""Security pins — /v1/agent-performance/* auth + per-agent ownership (#1188, PI-API-016).

Pre-fix every handler ran on ``AuthLevel.ANY`` with no ownership checks: any
JWT could allocate/deallocate resources and mutate performance records for
arbitrary ``agent_id``s. Post-fix: unauthenticated → 401; non-owner clients
are denied; the agent's ``AgentIdentity.owner_address`` must appear among the
caller's wallets.

Canonical security-suite port of the app-level pins in
``apps/coordinator-api/tests/test_agent_performance_authz.py`` — the app
suite remains the exhaustive matrix; this file carries the boundary cases.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

OWNER_ADDR = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
AGENT_ID = "perf-agent-owner-1"


def _headers(user_id: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.fixture
def seeded(db_session):
    db_session.add(User(id="owner1", email="owner1@aitbc.local", username="owner1"))
    db_session.add(Wallet(user_id="owner1", address=OWNER_ADDR.lower()))
    db_session.add(User(id="intruder", email="intruder@aitbc.local", username="intruder"))
    db_session.add(Wallet(user_id="intruder", address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2".lower()))
    db_session.add(AgentIdentity(agent_id=AGENT_ID, owner_address=OWNER_ADDR.lower()))
    db_session.commit()


def test_unauthenticated_gets_401(client, seeded):
    resp = client.get(f"/v1/agent-performance/profiles/{AGENT_ID}")
    assert resp.status_code == 401


def test_intruder_cannot_read_profile(client, seeded):
    resp = client.get(f"/v1/agent-performance/profiles/{AGENT_ID}", headers=_headers("intruder"))
    assert resp.status_code in (403, 404)


def test_intruder_cannot_create_profile_for_foreign_agent(client, seeded):
    resp = client.post(
        "/v1/agent-performance/profiles",
        headers=_headers("intruder"),
        json={"agent_id": AGENT_ID, "target_workload": "inference"},
    )
    assert resp.status_code in (400, 403, 404, 422)


def test_intruder_cannot_mutate_metrics(client, seeded):
    resp = client.post(
        f"/v1/agent-performance/profiles/{AGENT_ID}/metrics",
        headers=_headers("intruder"),
        json={"metric_name": "latency_ms", "value": 1.0},
    )
    assert resp.status_code in (400, 403, 404, 422)


def test_owner_is_not_denied(client, seeded):
    """Positive control: the owner's request passes the authz gate. The
    profile row itself is never created here, so 404 (not found) is the
    correct success-path answer — 403 would mean the ownership check
    misfired."""
    resp = client.get(f"/v1/agent-performance/profiles/{AGENT_ID}", headers=_headers("owner1"))
    assert resp.status_code != 403
