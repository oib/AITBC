"""PI-API-016 pins: /v1/agent-performance/* enforces auth + per-agent ownership.

Pre-fix every handler ran on AuthLevel.ANY with no ownership checks — any
JWT could allocate/deallocate resources and mutate performance records for
arbitrary agent_ids. Post-fix: admin/api_key bypass; other callers need the
agent's AgentIdentity owner_address among their wallets. Meta-learning
models carry no owner dimension and are admin-only.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token
from sqlmodel import select

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.agent_coordination.domain.agent_performance import (
    OptimizationTarget,
    ResourceAllocation,
)
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

OWNER_ADDR = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
AGENT_ID = "perf-agent-owner-1"


def _headers(user_id: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.fixture
def seeded(db_session):
    db_session.add(User(id="owner1", email="owner1@aitbc.local", username="owner1"))
    db_session.add(Wallet(user_id="owner1", address=OWNER_ADDR.lower()))
    db_session.add(User(id="intruder", email="intruder@aitbc.local", username="intruder"))
    db_session.add(Wallet(user_id="intruder", address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2".lower()))
    db_session.add(AgentIdentity(agent_id=AGENT_ID, owner_address=OWNER_ADDR.lower()))
    db_session.commit()
    return AGENT_ID


# --- unauthenticated / wrong-role gates ---


def test_unauthenticated_gets_401(client, seeded):
    resp = client.get(f"/v1/agent-performance/profiles/{AGENT_ID}")
    assert resp.status_code == 401


# --- cross-tenant reads and writes ---


def test_intruder_cannot_read_profile(client, seeded):
    resp = client.get(f"/v1/agent-performance/profiles/{AGENT_ID}", headers=_headers("intruder", "client"))
    assert resp.status_code == 403


def test_intruder_cannot_read_capabilities(client, seeded):
    resp = client.get(f"/v1/agent-performance/capabilities/{AGENT_ID}", headers=_headers("intruder", "client"))
    assert resp.status_code == 403


def test_intruder_cannot_read_analytics(client, seeded):
    resp = client.get(f"/v1/agent-performance/analytics/{AGENT_ID}", headers=_headers("intruder", "client"))
    assert resp.status_code == 403


def test_intruder_cannot_create_profile(client, seeded):
    resp = client.post(
        "/v1/agent-performance/profiles",
        headers=_headers("intruder", "client"),
        json={"agent_id": AGENT_ID, "agent_type": "agent"},
    )
    assert resp.status_code == 403


def test_intruder_cannot_update_metrics(client, seeded):
    resp = client.post(
        f"/v1/agent-performance/profiles/{AGENT_ID}/metrics",
        headers=_headers("intruder", "client"),
        json={"metrics": {"accuracy": 0.9}},
    )
    assert resp.status_code == 403


def test_intruder_cannot_allocate(client, seeded):
    resp = client.post(
        "/v1/agent-performance/resources/allocate",
        headers=_headers("intruder", "client"),
        json={"agent_id": AGENT_ID, "task_requirements": {"cpu_cores": 1}},
    )
    assert resp.status_code == 403


def test_intruder_cannot_create_capability(client, seeded):
    resp = client.post(
        "/v1/agent-performance/capabilities",
        headers=_headers("intruder", "client"),
        json={
            "agent_id": AGENT_ID,
            "capability_name": "x",
            "capability_type": "t",
            "domain_area": "d",
            "skill_level": 1.0,
        },
    )
    assert resp.status_code == 403


def test_intruder_cannot_optimize(client, seeded):
    resp = client.post(
        "/v1/agent-performance/optimize",
        headers=_headers("intruder", "client"),
        json={
            "agent_id": AGENT_ID,
            "target_metric": "accuracy",
            "current_performance": {"accuracy": 0.5},
        },
    )
    assert resp.status_code == 403


def test_agent_without_identity_is_denied_for_non_admin(client, seeded):
    """An agent_id with no AgentIdentity cannot be claimed by a non-admin."""
    resp = client.get("/v1/agent-performance/profiles/no-such-agent", headers=_headers("intruder", "client"))
    assert resp.status_code == 403


# --- deallocate resolves ownership through the persisted allocation ---


def test_intruder_cannot_deallocate_foreign_allocation(client, seeded, db_session):

    db_session.add(
        ResourceAllocation(
            allocation_id="alloc_foreign_1",
            agent_id=AGENT_ID,
            cpu_cores=1.0,
            memory_gb=1.0,
            status="active",
            optimization_target=OptimizationTarget.EFFICIENCY,
        )
    )
    db_session.commit()
    resp = client.post(
        "/v1/agent-performance/resources/alloc_foreign_1/deallocate",
        headers=_headers("intruder", "client"),
    )
    assert resp.status_code == 403
    row = db_session.exec(select(ResourceAllocation).where(ResourceAllocation.allocation_id == "alloc_foreign_1")).one()
    assert row.status == "active"


def test_list_allocations_scoped_to_owned_agents(client, seeded, db_session):
    """GET /resources must not leak other tenants' allocations to non-admins."""
    db_session.add(
        ResourceAllocation(
            allocation_id="alloc_visible_1",
            agent_id=AGENT_ID,
            cpu_cores=1.0,
            memory_gb=1.0,
            status="active",
            optimization_target=OptimizationTarget.EFFICIENCY,
        )
    )
    db_session.add(
        ResourceAllocation(
            allocation_id="alloc_hidden_1",
            agent_id="someone-elses-agent",
            cpu_cores=1.0,
            memory_gb=1.0,
            status="active",
            optimization_target=OptimizationTarget.EFFICIENCY,
        )
    )
    db_session.commit()
    resp = client.get("/v1/agent-performance/resources", headers=_headers("intruder", "client"))
    assert resp.status_code == 200
    ids = {r["allocation_id"] for r in resp.json()}
    assert "alloc_hidden_1" not in ids
    # owner sees their own allocation
    resp_owner = client.get("/v1/agent-performance/resources", headers=_headers("owner1", "client"))
    ids_owner = {r["allocation_id"] for r in resp_owner.json()}
    assert "alloc_visible_1" in ids_owner
    assert "alloc_hidden_1" not in ids_owner


# --- meta-learning has no owner dimension: admin-only ---


def test_meta_learning_requires_admin(client, seeded):
    resp = client.post(
        "/v1/agent-performance/meta-learning/models",
        headers=_headers("owner1", "client"),
        json={
            "model_name": "m",
            "base_algorithms": ["a"],
            "meta_strategy": "meta_learning",
            "adaptation_targets": ["t"],
        },
    )
    assert resp.status_code == 403
    resp_admin = client.post(
        "/v1/agent-performance/meta-learning/models",
        headers=_headers("admin1", "admin"),
        json={
            "model_name": "m",
            "base_algorithms": ["a"],
            "meta_strategy": "meta_learning",
            "adaptation_targets": ["t"],
        },
    )
    # admin passes the authz gate (downstream service may still fail — not 403)
    assert resp_admin.status_code != 403
