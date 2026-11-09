"""Service-layer tests for agent_coordination/services/creative_capabilities_service.py (#1289 residual).

Covers CreativityEnhancementEngine (create/enhance/evaluate against a real
in-memory SQLite session), IdeationAlgorithm (technique templates, idea
caps, fallback) and CrossDomainCreativeIntegrator (synthesis shape).
The CreativeCapability model is a plain JSON-column table — no migration.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.agent_coordination.domain.agent_performance import CreativeCapability
from coordinator_api.contexts.agent_coordination.services.creative_capabilities_service import (
    CreativityEnhancementEngine,
    CrossDomainCreativeIntegrator,
    IdeationAlgorithm,
)


@pytest.fixture
def engine() -> CreativityEnhancementEngine:
    return CreativityEnhancementEngine()


class TestCreateCapability:
    async def test_persists_with_derived_scores(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        cap = await engine.create_creative_capability(
            session=db_session,
            agent_id="agent-1",
            creative_domain="writing",
            capability_type="generative",
            generation_models=["gpt-x", "local-llm"],
            initial_score=0.5,
        )
        assert cap.capability_id.startswith("creative_")
        assert cap.status == "developing"
        assert cap.originality_score == pytest.approx(0.5)
        assert cap.novelty_score == pytest.approx(0.4)
        assert cap.coherence_score == pytest.approx(0.45)
        assert cap.generation_models == ["gpt-x", "local-llm"]
        db_session.expire_all()
        row = db_session.exec(select(CreativeCapability).where(CreativeCapability.capability_id == cap.capability_id)).first()
        assert row is not None and row.agent_id == "agent-1"

    async def test_capability_ids_unique(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        kwargs = {
            "session": db_session,
            "agent_id": "a",
            "creative_domain": "art",
            "capability_type": "generative",
            "generation_models": [],
        }
        c1 = await engine.create_creative_capability(**kwargs)
        c2 = await engine.create_creative_capability(**kwargs)
        assert c1.capability_id != c2.capability_id


class TestEnhanceCreativity:
    async def _cap(self, engine: CreativityEnhancementEngine, db_session: Session, score: float = 0.5):
        return await engine.create_creative_capability(
            session=db_session,
            agent_id="a",
            creative_domain="music",
            capability_type="compositional",
            generation_models=[],
            initial_score=score,
        )

    async def test_unknown_capability_raises(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            await engine.enhance_creativity(
                session=db_session, capability_id="creative_ghost", algorithm="x", training_cycles=10
            )

    async def test_scores_improve_and_cap_at_one(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        cap = await self._cap(engine, db_session, score=0.9)
        out = await engine.enhance_creativity(
            session=db_session, capability_id=cap.capability_id, algorithm="pso", training_cycles=500
        )
        # improvement = min(500/1000, 0.3) = 0.3
        assert out["new_originality_score"] == pytest.approx(min(0.9 + 0.3, 1.0))
        assert out["new_novelty_score"] == pytest.approx(min(0.9 * 0.8 + 0.3 * 0.8, 1.0))
        assert out["new_coherence_score"] == pytest.approx(min(0.9 * 0.9 + 0.3 * 0.9, 1.0))
        db_session.expire_all()
        assert cap.style_variety == 1 + 5  # int(500/100)

    async def test_zero_cycles_no_change(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        cap = await self._cap(engine, db_session, score=0.5)
        out = await engine.enhance_creativity(
            session=db_session, capability_id=cap.capability_id, algorithm="x", training_cycles=0
        )
        assert out["new_originality_score"] == pytest.approx(0.5)


class TestEvaluateCreation:
    async def _cap(self, engine: CreativityEnhancementEngine, db_session: Session):
        return await engine.create_creative_capability(
            session=db_session, agent_id="a", creative_domain="design", capability_type="analytical", generation_models=[]
        )

    async def test_unknown_capability_raises(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            await engine.evaluate_creation(session=db_session, capability_id="creative_ghost", creation_data={})

    async def test_default_scores_used_without_feedback(
        self, engine: CreativityEnhancementEngine, db_session: Session
    ) -> None:
        cap = await self._cap(engine, db_session)
        out = await engine.evaluate_creation(session=db_session, capability_id=cap.capability_id, creation_data={"x": 1})
        # defaults: 0.6,0.5,0.7,0.6 -> avg 0.6
        assert out["overall_score"] == pytest.approx(0.6)
        assert out["total_creations"] == 1
        assert out["evaluation_scores"]["aesthetic"] == 0.6

    async def test_expert_feedback_overrides(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        cap = await self._cap(engine, db_session)
        out = await engine.evaluate_creation(
            session=db_session,
            capability_id=cap.capability_id,
            creation_data={},
            expert_feedback={"originality": 1.0, "novelty": 0.0},
        )
        assert out["overall_score"] == pytest.approx(0.5)
        assert out["evaluation_scores"] == {"originality": 1.0, "novelty": 0.0}

    async def test_output_quality_running_average(self, engine: CreativityEnhancementEngine, db_session: Session) -> None:
        cap = await self._cap(engine, db_session)
        # first eval avg 1.0 -> (0 + 5)/2 = 2.5; second eval avg 0.0 -> (2.5 + 0)/2 = 1.25
        await engine.evaluate_creation(
            session=db_session, capability_id=cap.capability_id, creation_data={}, expert_feedback={"s": 1.0}
        )
        await engine.evaluate_creation(
            session=db_session, capability_id=cap.capability_id, creation_data={}, expert_feedback={"s": 0.0}
        )
        db_session.expire_all()
        assert cap.creations_generated == 2
        assert cap.output_quality == pytest.approx(1.25)
        assert cap.last_evaluation is not None


class TestIdeationAlgorithm:
    async def test_scamper_ideas(self) -> None:
        algo = IdeationAlgorithm()
        out = await algo.generate_ideas(problem_statement="reduce churn", domain="saas", technique="scamper", num_ideas=3)
        assert out["total_generated"] == 3
        assert [i["action"] for i in out["ideas"]] == ["Substitute", "Combine", "Adapt"]
        assert out["ideas"][0]["feasibility"] == pytest.approx(0.7)
        assert out["ideas"][2]["novelty"] == pytest.approx(0.8 - 2 * 0.08)

    async def test_num_ideas_capped_at_action_count(self) -> None:
        algo = IdeationAlgorithm()
        out = await algo.generate_ideas(problem_statement="p", domain="d", technique="scamper", num_ideas=99)
        assert out["total_generated"] == 7  # scamper has 7 actions

    async def test_unknown_technique_falls_back(self) -> None:
        algo = IdeationAlgorithm()
        out = await algo.generate_ideas(problem_statement="p", domain="d", technique="bogus", num_ideas=2)
        assert out["technique"] == "bogus"
        assert out["total_generated"] == 2
        assert out["ideas"][0]["action"] == "Combine"

    async def test_constraints_echoed(self) -> None:
        algo = IdeationAlgorithm()
        out = await algo.generate_ideas(
            problem_statement="p", domain="d", technique="triz", num_ideas=1, constraints={"budget": 100}
        )
        assert out["constraints"] == {"budget": 100}
        assert out["ideas"][0]["action"] == "Segmentation"


class TestCrossDomainIntegrator:
    async def test_synthesis_shape(self, db_session: Session) -> None:
        integ = CrossDomainCreativeIntegrator()
        out = await integ.generate_cross_domain_synthesis(
            session=db_session,
            agent_id="agent-9",
            primary_domain="biology",
            secondary_domains=["engineering", "music"],
            synthesis_goal="bio-inspired instruments",
        )
        assert out["synthesis_id"].startswith("synth_")
        assert out["domains"] == ["biology", "engineering", "music"]
        assert len(out["connections"]) == 2
        assert out["connections"][0]["secondary_domain"] == "engineering"
        assert out["novelty_score"] == pytest.approx(0.75)
        assert len(out["potential_applications"]) == 2

    async def test_empty_secondary_domains(self, db_session: Session) -> None:
        integ = CrossDomainCreativeIntegrator()
        out = await integ.generate_cross_domain_synthesis(
            session=db_session, agent_id="a", primary_domain="math", secondary_domains=[], synthesis_goal="g"
        )
        assert out["connections"] == []
        assert "other domains" in out["potential_applications"][0]
