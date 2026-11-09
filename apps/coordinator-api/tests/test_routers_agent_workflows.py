"""Tests for /v1/agents/workflows* — AdminDep gating and ownership branches (#1289).

``agent_router`` was mounted 2026-09-11 after sitting as dead code; this file
pins the auth surface (admin-only via ``AdminDep``) and the owner/public
visibility rules on the workflow endpoints. Execution is pinned at the
``enable_orchestration_simulation`` gate (default off → 501).

Defect history: ``POST /workflows`` 500'd for every payload —
``AgentWorkflowCreate.tags`` is ``list[str]`` while ``AIAgentWorkflow.tags``
is a ``str`` column holding a JSON string (#1289 finding, fixed #1292 by
serializing at the router boundary). CRUD tests still seed
``AIAgentWorkflow`` rows directly for isolation.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.agent_coordination.domain.agent import AIAgentWorkflow

ADMIN_A = "admin-a"
ADMIN_B = "admin-b"


def _headers(sub: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin_a() -> dict[str, str]:
    return _headers(ADMIN_A, "admin")


def _admin_b() -> dict[str, str]:
    return _headers(ADMIN_B, "admin")


def _client() -> dict[str, str]:
    return _headers("client-1", "client")


def _workflow_body(name: str = "wf-1", is_public: bool = False) -> dict:
    return {
        "name": name,
        "description": "coverage sweep",
        "steps": {"step_1": {"action": "noop"}},
        "is_public": is_public,
    }


def _seed_workflow(db_session: Session, owner_id: str, name: str = "wf", is_public: bool = False) -> str:
    """Insert a workflow row directly (bypasses the API boundary)."""
    wf = AIAgentWorkflow(
        owner_id=owner_id,
        name=name,
        description="seeded",
        steps={"step_1": {"action": "noop"}},
        is_public=is_public,
        tags="[]",
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)
    return wf.id


@pytest.mark.unit
class TestWorkflowAuthGating:
    def test_create_requires_auth(self, client: TestClient) -> None:
        resp = client.post("/v1/agents/workflows", json=_workflow_body())
        assert resp.status_code == 401

    def test_create_rejects_client_role(self, client: TestClient) -> None:
        resp = client.post("/v1/agents/workflows", json=_workflow_body(), headers=_client())
        assert resp.status_code == 403

    def test_create_admin_success(self, client: TestClient) -> None:
        body = _workflow_body()
        body["tags"] = ["alpha", "beta"]
        resp = client.post("/v1/agents/workflows", json=body, headers=_admin_a())
        assert resp.status_code == 200
        assert resp.json()["owner_id"] == ADMIN_A
        # tags column is a JSON string; the list must round-trip through it.
        assert json.loads(resp.json()["tags"]) == ["alpha", "beta"]


@pytest.mark.unit
class TestWorkflowCrud:
    def test_get_missing_is_404(self, client: TestClient) -> None:
        resp = client.get("/v1/agents/workflows/does-not-exist", headers=_admin_a())
        assert resp.status_code == 404

    def test_owner_reads_own_private_workflow(self, client: TestClient, db_session: Session) -> None:
        wf_id = _seed_workflow(db_session, ADMIN_A, "private-wf")
        resp = client.get(f"/v1/agents/workflows/{wf_id}", headers=_admin_a())
        assert resp.status_code == 200
        assert resp.json()["name"] == "private-wf"

    def test_other_admin_denied_private_but_reads_public(self, client: TestClient, db_session: Session) -> None:
        private_id = _seed_workflow(db_session, ADMIN_A, "a-private")
        public_id = _seed_workflow(db_session, ADMIN_A, "a-public", is_public=True)

        resp = client.get(f"/v1/agents/workflows/{private_id}", headers=_admin_b())
        assert resp.status_code == 403

        resp = client.get(f"/v1/agents/workflows/{public_id}", headers=_admin_b())
        assert resp.status_code == 200

    def test_list_shows_own_and_public_only(self, client: TestClient, db_session: Session) -> None:
        a_private = _seed_workflow(db_session, ADMIN_A, "a-priv")
        a_public = _seed_workflow(db_session, ADMIN_A, "a-pub", is_public=True)
        b_private = _seed_workflow(db_session, ADMIN_B, "b-priv")

        resp = client.get("/v1/agents/workflows", headers=_admin_a())
        assert resp.status_code == 200
        ids = {w["id"] for w in resp.json()}
        assert a_private in ids and a_public in ids
        assert b_private not in ids

    def test_list_owner_id_filter(self, client: TestClient, db_session: Session) -> None:
        a_id = _seed_workflow(db_session, ADMIN_A, "a-only")
        _seed_workflow(db_session, ADMIN_B, "b-only", is_public=True)

        resp = client.get(f"/v1/agents/workflows?owner_id={ADMIN_A}", headers=_admin_a())
        assert resp.status_code == 200
        ids = {w["id"] for w in resp.json()}
        assert ids == {a_id}

    def test_update_owner_only(self, client: TestClient, db_session: Session) -> None:
        wf_id = _seed_workflow(db_session, ADMIN_A, "upd-me")

        resp = client.put(f"/v1/agents/workflows/{wf_id}", json={"name": "renamed"}, headers=_admin_a())
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

        resp = client.put(f"/v1/agents/workflows/{wf_id}", json={"name": "hijack"}, headers=_admin_b())
        assert resp.status_code == 403

        resp = client.put("/v1/agents/workflows/missing", json={"name": "x"}, headers=_admin_a())
        assert resp.status_code == 404

    def test_update_tags_serialized(self, client: TestClient, db_session: Session) -> None:
        """PUT tags list must hit the same JSON-string boundary as POST (#1292)."""
        wf_id = _seed_workflow(db_session, ADMIN_A, "tags-me")

        resp = client.put(
            f"/v1/agents/workflows/{wf_id}",
            json={"tags": ["x", "y"]},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        assert json.loads(resp.json()["tags"]) == ["x", "y"]

        # Explicit null tags must not violate the NOT NULL column.
        resp = client.put(
            f"/v1/agents/workflows/{wf_id}",
            json={"tags": None},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        assert json.loads(resp.json()["tags"]) == ["x", "y"]

    def test_delete_owner_only(self, client: TestClient, db_session: Session) -> None:
        wf_id = _seed_workflow(db_session, ADMIN_A, "del-me")

        resp = client.delete(f"/v1/agents/workflows/{wf_id}", headers=_admin_b())
        assert resp.status_code == 403

        resp = client.delete(f"/v1/agents/workflows/{wf_id}", headers=_admin_a())
        assert resp.status_code == 200

        resp = client.get(f"/v1/agents/workflows/{wf_id}", headers=_admin_a())
        assert resp.status_code == 404


@pytest.mark.unit
class TestWorkflowExecuteGate:
    def test_execute_returns_501_while_simulation_disabled(self, client: TestClient) -> None:
        """enable_orchestration_simulation defaults off; the gate fires before lookup."""
        resp = client.post(
            "/v1/agents/workflows/any-id/execute",
            json={"workflow_id": "any-id", "inputs": {}},
            headers=_admin_a(),
        )
        assert resp.status_code == 501
        assert "simulation" in resp.json()["detail"].lower()
