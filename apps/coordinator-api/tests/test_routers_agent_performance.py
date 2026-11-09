"""Router tests for /v1/agent-performance/* (#1289 round 9).

Ownership model (PI-API-016): non-admin callers must control the wallet
that owns the agent's AgentIdentity row; admin bypasses; meta-learning
endpoints are admin-only. AgentCapability has NO ``status`` field — the
router reads ``capability.status`` on create and list, which 500s
whenever a capability row is returned (strict-xfail, defect pinned).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.agent_coordination.domain.agent_performance import (
    AgentCapability,
    LearningStrategy,
    MetaLearningModel,
    OptimizationTarget,
    ResourceAllocation,
)
from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.user import Wallet

ADMIN = "admin-a"
OWNER_SUB = "client-1"  # seeded user in conftest
OWNER_ADDR = "0x" + "ab" * 20
OTHER_ADDR = "0x" + "cd" * 20
AGENT = "ag-perf-1"


def _headers(sub: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers(ADMIN, "admin")


def _owner() -> dict[str, str]:
    return _headers(OWNER_SUB, "client")


def _stranger() -> dict[str, str]:
    return _headers("client-2", "client")


@pytest.fixture
def owned_agent(db_session: Session) -> None:
    """AgentIdentity owned by OWNER_SUB's wallet + an allocation row."""
    db_session.add(Wallet(user_id=OWNER_SUB, address=OWNER_ADDR))
    db_session.add(AgentIdentity(agent_id=AGENT, owner_address=OWNER_ADDR))
    db_session.commit()


def _profile_body(agent_id: str = AGENT) -> dict:
    return {"agent_id": agent_id, "agent_type": "trainer", "initial_metrics": {"accuracy": 0.9}}


class TestProfileEndpoints:
    def test_create_requires_auth(self, client: TestClient) -> None:
        assert client.post("/v1/agent-performance/profiles", json=_profile_body()).status_code == 401

    def test_create_admin_success(self, client: TestClient, db_session: Session) -> None:
        resp = client.post("/v1/agent-performance/profiles", json=_profile_body("ag-admin"), headers=_admin())
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == "ag-admin"
        assert body["performance_metrics"] == {"accuracy": 0.9}

    def test_create_forbidden_without_identity(self, client: TestClient) -> None:
        # non-admin + no AgentIdentity row -> 403 even for own sub
        resp = client.post("/v1/agent-performance/profiles", json=_profile_body("ag-noident"), headers=_owner())
        assert resp.status_code == 403

    def test_create_owner_success(self, client: TestClient, owned_agent: None) -> None:
        resp = client.post("/v1/agent-performance/profiles", json=_profile_body(), headers=_owner())
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == AGENT

    def test_get_profile_404_and_owner(self, client: TestClient, owned_agent: None) -> None:
        assert client.get("/v1/agent-performance/profiles/ghost", headers=_admin()).status_code == 404
        client.post("/v1/agent-performance/profiles", json=_profile_body(), headers=_owner())
        resp = client.get(f"/v1/agent-performance/profiles/{AGENT}", headers=_owner())
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == AGENT
        # stranger (no wallet match) -> 403
        assert client.get(f"/v1/agent-performance/profiles/{AGENT}", headers=_stranger()).status_code == 403

    def test_update_metrics(self, client: TestClient, owned_agent: None) -> None:
        resp = client.post(
            f"/v1/agent-performance/profiles/{AGENT}/metrics",
            json={"metrics": {"accuracy": 0.8}},
            headers=_owner(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["profile_id"].startswith("perf_")
        # second update exercises the existing-profile branch
        resp2 = client.post(
            f"/v1/agent-performance/profiles/{AGENT}/metrics",
            json={"metrics": {"accuracy": 0.95}},
            headers=_admin(),
        )
        assert resp2.status_code == 200
        assert resp2.json()["overall_score"] > 0


class TestMetaLearningEndpoints:
    def _model_body(self) -> dict:
        return {
            "model_name": "m1",
            "base_algorithms": ["cnn"],
            "meta_strategy": "meta_learning",
            "adaptation_targets": ["text_generation"],
        }

    def test_create_requires_admin(self, client: TestClient) -> None:
        assert (
            client.post("/v1/agent-performance/meta-learning/models", json=self._model_body(), headers=_owner()).status_code
            == 403
        )
        resp = client.post("/v1/agent-performance/meta-learning/models", json=self._model_body())
        assert resp.status_code == 401

    def test_create_and_status(self, client: TestClient) -> None:
        resp = client.post("/v1/agent-performance/meta-learning/models", json=self._model_body(), headers=_admin())
        assert resp.status_code == 200
        body = resp.json()
        assert body["model_id"].startswith("meta_")
        assert body["status"] in {"training", "ready"}

    def test_adapt_admin_only_and_404(self, client: TestClient, db_session: Session) -> None:
        assert (
            client.post("/v1/agent-performance/meta-learning/models/ghost/adapt", json={}, headers=_owner()).status_code == 403
        )
        # unknown model -> ValueError -> 404 for admin
        resp = client.post("/v1/agent-performance/meta-learning/models/ghost/adapt", json={"task": "x"}, headers=_admin())
        assert resp.status_code == 404

    def test_adapt_ready_model(self, client: TestClient, db_session: Session) -> None:
        from datetime import UTC, datetime

        model = MetaLearningModel(
            model_id="meta_r1",
            model_name="r",
            base_algorithms=["cnn"],
            meta_strategy=LearningStrategy.META_LEARNING,
            adaptation_targets=["reasoning"],
            status="ready",
            meta_accuracy=0.8,
            adaptation_speed=0.9,
            trained_at=datetime.now(UTC),
        )
        db_session.add(model)
        db_session.commit()
        resp = client.post(
            "/v1/agent-performance/meta-learning/models/meta_r1/adapt",
            json={"task": "new"},
            headers=_admin(),
        )
        assert resp.status_code == 200
        assert resp.json()["steps_used"] == 10


class TestResourceEndpoints:
    def _alloc_body(self, agent_id: str = AGENT) -> dict:
        return {
            "agent_id": agent_id,
            "task_requirements": {"task_type": "training"},
            "optimization_target": "efficiency",
        }

    _alloc_seq = 0

    def _seed_allocation(self, db_session: Session, agent_id: str = AGENT) -> str:
        from datetime import UTC, datetime

        type(self)._alloc_seq += 1
        alloc = ResourceAllocation(
            allocation_id=f"alloc_test{type(self)._alloc_seq}",
            agent_id=agent_id,
            cpu_cores=2.0,
            memory_gb=4.0,
            gpu_count=1.0,
            storage_gb=50.0,
            network_bandwidth=100.0,
            optimization_target=OptimizationTarget.EFFICIENCY,
            status="allocated",
            allocated_at=datetime.now(UTC),
        )
        db_session.add(alloc)
        db_session.commit()
        return alloc.allocation_id

    def test_allocate_owner_and_admin(self, client: TestClient, owned_agent: None) -> None:
        resp = client.post("/v1/agent-performance/resources/allocate", json=self._alloc_body(), headers=_owner())
        assert resp.status_code == 200
        assert resp.json()["allocation_id"].startswith("alloc_")
        assert resp.json()["status"] == "allocated"
        # stranger -> 403
        assert (
            client.post("/v1/agent-performance/resources/allocate", json=self._alloc_body(), headers=_stranger()).status_code
            == 403
        )

    def test_list_scoped_to_owner(self, client: TestClient, owned_agent: None, db_session: Session) -> None:
        self._seed_allocation(db_session, AGENT)
        self._seed_allocation(db_session, "ag-other")
        # admin sees both
        admin_rows = client.get("/v1/agent-performance/resources", headers=_admin()).json()
        assert {r["agent_id"] for r in admin_rows} == {AGENT, "ag-other"}
        # owner sees only own agent's allocations
        owner_rows = client.get("/v1/agent-performance/resources", headers=_owner()).json()
        assert {r["agent_id"] for r in owner_rows} == {AGENT}

    def test_agent_id_filter_non_owner_403(self, client: TestClient, owned_agent: None, db_session: Session) -> None:
        self._seed_allocation(db_session, AGENT)
        self._seed_allocation(db_session, "ag-other")
        # agent_id filter on someone else's agent must be a 403, not a 500
        assert (
            client.get("/v1/agent-performance/resources", params={"agent_id": "ag-other"}, headers=_owner()).status_code == 403
        )

    def test_deallocate_lifecycle(self, client: TestClient, owned_agent: None, db_session: Session) -> None:
        aid = self._seed_allocation(db_session)
        assert client.post(f"/v1/agent-performance/resources/{aid}/deallocate", headers=_admin()).status_code == 200
        # second deallocate -> 409
        assert client.post(f"/v1/agent-performance/resources/{aid}/deallocate", headers=_admin()).status_code == 409
        # missing -> 404
        assert client.post("/v1/agent-performance/resources/alloc_nope/deallocate", headers=_admin()).status_code == 404
        # stranger cannot deallocate owner's allocation -> 403
        aid2 = self._seed_allocation(db_session)
        assert client.post(f"/v1/agent-performance/resources/{aid2}/deallocate", headers=_stranger()).status_code == 403


class TestOptimizeAndCapabilityEndpoints:
    def test_optimize_completes(self, client: TestClient, owned_agent: None) -> None:
        resp = client.post(
            "/v1/agent-performance/optimize",
            json={
                "agent_id": AGENT,
                "target_metric": "accuracy",
                "current_performance": {"accuracy": 0.8},
            },
            headers=_owner(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["optimization_id"].startswith("opt_")

    def test_analytics(self, client: TestClient, owned_agent: None) -> None:
        resp = client.get(f"/v1/agent-performance/analytics/{AGENT}", headers=_owner())
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == AGENT
        assert resp.json()["capability_count"] == 0

    @pytest.mark.xfail(
        strict=True,
        reason="defect #1324: router reads capability.status but AgentCapability has no status field -> AttributeError -> 500 on create",
    )
    def test_create_capability(self, client: TestClient, owned_agent: None) -> None:
        resp = client.post(
            "/v1/agent-performance/capabilities",
            json={
                "agent_id": AGENT,
                "capability_name": "summarize",
                "capability_type": "nlp",
                "domain_area": "text",
                "skill_level": 8.0,
            },
            headers=_owner(),
        )
        assert resp.status_code == 200
        assert resp.json()["capability_id"].startswith("cap_")

    def test_list_capabilities_empty_ok(self, client: TestClient, owned_agent: None) -> None:
        resp = client.get(f"/v1/agent-performance/capabilities/{AGENT}", headers=_owner())
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.xfail(
        strict=True,
        reason="defect #1324: same missing capability.status field — listing an agent that HAS capability rows 500s",
    )
    def test_list_capabilities_with_rows(self, client: TestClient, owned_agent: None, db_session: Session) -> None:
        db_session.add(
            AgentCapability(
                capability_id="cap_seed1",
                agent_id=AGENT,
                capability_name="seed",
                capability_type="t",
                domain_area="d",
                skill_level=5.0,
            )
        )
        db_session.commit()
        resp = client.get(f"/v1/agent-performance/capabilities/{AGENT}", headers=_owner())
        assert resp.status_code == 200
        assert resp.json()[0]["capability_name"] == "seed"

    def test_optimize_forbidden_stranger(self, client: TestClient, owned_agent: None) -> None:
        resp = client.post(
            "/v1/agent-performance/optimize",
            json={"agent_id": AGENT, "target_metric": "accuracy", "current_performance": {"accuracy": 0.5}},
            headers=_stranger(),
        )
        assert resp.status_code == 403
