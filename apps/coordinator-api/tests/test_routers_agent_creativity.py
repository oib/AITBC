"""Tests for /v1/agent-creativity/* — AdminDep gating and engine delegation (#1289 round 4).

``agent_creativity`` (6 endpoints) was mounted 2026-09-11 after a period of
unauthenticated writes; every handler now takes ``AdminDep`` and constructs
its engine inline, so the engines are patched at the router module
namespace. The ``GET /capabilities/{agent_id}`` list endpoint hits the real
``creative_capabilities`` table on the in-memory session.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.agent_coordination.domain.agent_performance import CreativeCapability
from coordinator_api.contexts.agent_coordination.routers import agent_creativity as rc

BASE = "/v1/agent-creativity"


def _headers(sub: str = "admin-a", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers()


def _client() -> dict[str, str]:
    return _headers("client-1", "client")


def _capability_ns(**over: Any) -> SimpleNamespace:
    base = {
        "capability_id": "cap-1",
        "agent_id": "agent-1",
        "creative_domain": "design",
        "capability_type": "generative",
        "originality_score": 0.7,
        "novelty_score": 0.6,
        "aesthetic_quality": 4.0,
        "coherence_score": 0.8,
        "style_variety": 3,
        "creative_specializations": ["ui"],
        "status": "developing",
    }
    base.update(over)
    return SimpleNamespace(**base)


class _FakeEngine:
    def __init__(self, **kwargs: Any) -> None:
        self.create_creative_capability = AsyncMock(return_value=_capability_ns())
        self.enhance_creativity = AsyncMock(return_value={"enhanced": True})
        self.evaluate_creation = AsyncMock(return_value={"score": 0.9})


class _FakeIdeation:
    def __init__(self, **kwargs: Any) -> None:
        self.generate_ideas = AsyncMock(return_value={"ideas": ["idea-1"]})


class _FakeIntegrator:
    def __init__(self, **kwargs: Any) -> None:
        self.generate_cross_domain_synthesis = AsyncMock(return_value={"synthesis": "novel"})


@pytest.fixture
def engines(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    fake_engine = _FakeEngine()
    fake_ideation = _FakeIdeation()
    fake_integrator = _FakeIntegrator()
    monkeypatch.setattr(rc, "CreativityEnhancementEngine", lambda *a, **k: fake_engine)
    monkeypatch.setattr(rc, "IdeationAlgorithm", lambda *a, **k: fake_ideation)
    monkeypatch.setattr(rc, "CrossDomainCreativeIntegrator", lambda *a, **k: fake_integrator)
    return {"engine": fake_engine, "ideation": fake_ideation, "integrator": fake_integrator}


def _seed_capability(db_session: Session, agent_id: str, domain: str = "art") -> CreativeCapability:
    cap = CreativeCapability(
        capability_id=f"cap-{agent_id}-{domain}",
        agent_id=agent_id,
        creative_domain=domain,
        capability_type="generative",
        originality_score=0.5,
        novelty_score=0.5,
        aesthetic_quality=3.0,
        coherence_score=0.5,
    )
    db_session.add(cap)
    db_session.commit()
    db_session.refresh(cap)
    return cap


class TestAuthGating:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("post", "/capabilities"),
            ("post", "/capabilities/cap-1/enhance"),
            ("post", "/capabilities/cap-1/evaluate"),
            ("post", "/ideation/generate"),
            ("post", "/synthesis/cross-domain"),
            ("get", "/capabilities/agent-1"),
        ],
    )
    def test_no_token_rejected(self, client: TestClient, method: str, path: str) -> None:
        if method == "get":
            resp = client.get(f"{BASE}{path}")
        else:
            resp = client.post(f"{BASE}{path}", json={})
        assert resp.status_code in (401, 403, 422)

    def test_client_role_forbidden(self, client: TestClient, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/capabilities",
            json={
                "agent_id": "a1",
                "creative_domain": "design",
                "capability_type": "generative",
                "generation_models": ["m1"],
            },
            headers=_client(),
        )
        assert resp.status_code == 403


class TestCreateCapability:
    def test_success_shape(self, client: TestClient, db_session: Session, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/capabilities",
            json={
                "agent_id": "agent-9",
                "creative_domain": "innovation",
                "capability_type": "analytical",
                "generation_models": ["m1", "m2"],
                "initial_score": 0.4,
            },
            headers=_admin(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["capability_id"] == "cap-1"
        assert data["creative_domain"] == "design"
        kwargs = engines["engine"].create_creative_capability.await_args.kwargs
        assert kwargs["agent_id"] == "agent-9"
        assert kwargs["generation_models"] == ["m1", "m2"]

    def test_initial_score_out_of_range_422(self, client: TestClient, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/capabilities",
            json={
                "agent_id": "a",
                "creative_domain": "d",
                "capability_type": "t",
                "generation_models": [],
                "initial_score": 1.5,
            },
            headers=_admin(),
        )
        assert resp.status_code == 422

    def test_engine_error_500(self, client: TestClient, engines: dict[str, Any]) -> None:
        engines["engine"].create_creative_capability.side_effect = RuntimeError("boom")
        resp = client.post(
            f"{BASE}/capabilities",
            json={
                "agent_id": "a",
                "creative_domain": "d",
                "capability_type": "t",
                "generation_models": [],
            },
            headers=_admin(),
        )
        assert resp.status_code == 500


class TestEnhanceAndEvaluate:
    def test_enhance_success(self, client: TestClient, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/capabilities/cap-1/enhance",
            json={"algorithm": "triz", "training_cycles": 50},
            headers=_admin(),
        )
        assert resp.status_code == 200
        assert resp.json() == {"enhanced": True}
        kwargs = engines["engine"].enhance_creativity.await_args.kwargs
        assert kwargs["capability_id"] == "cap-1"
        assert kwargs["algorithm"] == "triz"

    def test_enhance_not_found_404(self, client: TestClient, engines: dict[str, Any]) -> None:
        engines["engine"].enhance_creativity.side_effect = ValueError("capability not found")
        resp = client.post(f"{BASE}/capabilities/cap-x/enhance", json={"algorithm": "x"}, headers=_admin())
        assert resp.status_code == 404

    def test_enhance_engine_error_500(self, client: TestClient, engines: dict[str, Any]) -> None:
        engines["engine"].enhance_creativity.side_effect = RuntimeError("boom")
        resp = client.post(f"{BASE}/capabilities/cap-1/enhance", json={"algorithm": "x"}, headers=_admin())
        assert resp.status_code == 500

    def test_evaluate_success(self, client: TestClient, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/capabilities/cap-1/evaluate",
            json={"creation_data": {"text": "poem"}, "expert_feedback": {"quality": 0.9}},
            headers=_admin(),
        )
        assert resp.status_code == 200
        kwargs = engines["engine"].evaluate_creation.await_args.kwargs
        assert kwargs["creation_data"] == {"text": "poem"}
        assert kwargs["expert_feedback"] == {"quality": 0.9}

    def test_evaluate_not_found_404(self, client: TestClient, engines: dict[str, Any]) -> None:
        engines["engine"].evaluate_creation.side_effect = ValueError("missing")
        resp = client.post(f"{BASE}/capabilities/cap-x/evaluate", json={"creation_data": {}}, headers=_admin())
        assert resp.status_code == 404


class TestIdeationAndSynthesis:
    def test_ideation_generate(self, client: TestClient, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/ideation/generate",
            json={
                "problem_statement": "reduce latency",
                "domain": "systems",
                "technique": "triz",
                "num_ideas": 3,
            },
            headers=_admin(),
        )
        assert resp.status_code == 200
        assert resp.json()["ideas"] == ["idea-1"]
        kwargs = engines["ideation"].generate_ideas.await_args.kwargs
        assert kwargs["technique"] == "triz"
        assert kwargs["num_ideas"] == 3

    def test_ideation_num_ideas_bounds(self, client: TestClient, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/ideation/generate",
            json={"problem_statement": "p", "domain": "d", "num_ideas": 50},
            headers=_admin(),
        )
        assert resp.status_code == 422

    def test_synthesis_success(self, client: TestClient, engines: dict[str, Any]) -> None:
        resp = client.post(
            f"{BASE}/synthesis/cross-domain",
            json={
                "agent_id": "a1",
                "primary_domain": "biology",
                "secondary_domains": ["engineering"],
                "synthesis_goal": "novel sensor",
            },
            headers=_admin(),
        )
        assert resp.status_code == 200
        kwargs = engines["integrator"].generate_cross_domain_synthesis.await_args.kwargs
        assert kwargs["secondary_domains"] == ["engineering"]

    def test_synthesis_value_error_400(self, client: TestClient, engines: dict[str, Any]) -> None:
        engines["integrator"].generate_cross_domain_synthesis.side_effect = ValueError("bad domains")
        resp = client.post(
            f"{BASE}/synthesis/cross-domain",
            json={
                "agent_id": "a1",
                "primary_domain": "x",
                "secondary_domains": [],
                "synthesis_goal": "g",
            },
            headers=_admin(),
        )
        assert resp.status_code == 400


class TestListCapabilities:
    def test_filters_by_agent_id(self, client: TestClient, db_session: Session) -> None:
        _seed_capability(db_session, "agent-a", "art")
        _seed_capability(db_session, "agent-a", "music")
        _seed_capability(db_session, "agent-b", "design")
        resp = client.get(f"{BASE}/capabilities/agent-a", headers=_admin())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(c["agent_id"] == "agent-a" for c in data)
        assert {c["creative_domain"] for c in data} == {"art", "music"}

    def test_empty_for_unknown_agent(self, client: TestClient, db_session: Session) -> None:
        _seed_capability(db_session, "agent-a")
        resp = client.get(f"{BASE}/capabilities/nobody", headers=_admin())
        assert resp.status_code == 200
        assert resp.json() == []
