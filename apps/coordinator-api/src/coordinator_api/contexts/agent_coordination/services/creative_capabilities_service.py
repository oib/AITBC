"""
Creative capabilities service for agent creativity enhancement, ideation, and cross-domain synthesis.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from coordinator_api.contexts.agent_coordination.domain.agent_performance import CreativeCapability


class CreativityEnhancementEngine:
    """Engine for creating and enhancing creative capabilities."""

    async def create_creative_capability(
        self,
        *,
        session: Session,
        agent_id: str,
        creative_domain: str,
        capability_type: str,
        generation_models: list[str],
        initial_score: float = 0.5,
    ) -> CreativeCapability:
        """Initialize a new creative capability for an agent."""
        capability_id = f"creative_{uuid4().hex[:8]}"
        capability = CreativeCapability(
            capability_id=capability_id,
            agent_id=agent_id,
            creative_domain=creative_domain,
            capability_type=capability_type,
            originality_score=initial_score,
            novelty_score=initial_score * 0.8,
            coherence_score=initial_score * 0.9,
            generation_models=generation_models,
            status="developing",
        )
        session.add(capability)
        session.commit()
        session.refresh(capability)
        return capability

    async def enhance_creativity(
        self, *, session: Session, capability_id: str, algorithm: str, training_cycles: int
    ) -> dict[str, Any]:
        """Enhance a creative capability using the specified algorithm."""
        capability = (
            session.execute(select(CreativeCapability).where(CreativeCapability.capability_id == capability_id))
            .scalars()
            .first()
        )
        if not capability:
            raise ValueError(f"Creative capability {capability_id} not found")
        improvement = min(training_cycles / 1000.0, 0.3)
        capability.originality_score = min(capability.originality_score + improvement, 1.0)
        capability.novelty_score = min(capability.novelty_score + improvement * 0.8, 1.0)
        capability.coherence_score = min(capability.coherence_score + improvement * 0.9, 1.0)
        capability.style_variety = min(capability.style_variety + int(training_cycles / 100), 10)
        capability.updated_at = datetime.now(UTC)
        session.commit()
        return {
            "capability_id": capability_id,
            "algorithm": algorithm,
            "training_cycles": training_cycles,
            "new_originality_score": capability.originality_score,
            "new_novelty_score": capability.novelty_score,
            "new_coherence_score": capability.coherence_score,
            "enhanced_at": datetime.now(UTC).isoformat(),
        }

    async def evaluate_creation(
        self,
        *,
        session: Session,
        capability_id: str,
        creation_data: dict[str, Any],
        expert_feedback: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a creative output and update capability metrics."""
        capability = (
            session.execute(select(CreativeCapability).where(CreativeCapability.capability_id == capability_id))
            .scalars()
            .first()
        )
        if not capability:
            raise ValueError(f"Creative capability {capability_id} not found")
        scores: dict[str, float] = {}
        if expert_feedback:
            scores = expert_feedback
        else:
            scores = {"originality": 0.6, "novelty": 0.5, "coherence": 0.7, "aesthetic": 0.6}
        avg = sum(scores.values()) / len(scores) if scores else 0.5
        capability.creations_generated += 1
        capability.last_evaluation = datetime.now(UTC)
        capability.output_quality = (capability.output_quality + avg * 5.0) / 2.0
        capability.updated_at = datetime.now(UTC)
        session.commit()
        return {
            "capability_id": capability_id,
            "evaluation_scores": scores,
            "overall_score": avg,
            "total_creations": capability.creations_generated,
            "evaluated_at": datetime.now(UTC).isoformat(),
        }


class IdeationAlgorithm:
    """Algorithm for generating innovative ideas using specialized techniques."""

    async def generate_ideas(
        self,
        *,
        problem_statement: str,
        domain: str,
        technique: str = "scamper",
        num_ideas: int = 5,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate innovative ideas using the specified technique."""
        technique_actions: dict[str, list[str]] = {
            "scamper": ["Substitute", "Combine", "Adapt", "Modify", "Put to other use", "Eliminate", "Reverse"],
            "triz": ["Segmentation", "Taking out", "Local quality", "Asymmetry", "Merging", "Universality"],
            "six_thinking_hats": [
                "White (facts)",
                "Red (emotions)",
                "Black (caution)",
                "Yellow (optimism)",
                "Green (creativity)",
                "Blue (process)",
            ],
            "first_principles": ["Identify assumptions", "Break down fundamentals", "Rebuild from scratch"],
            "biomimicry": ["Nature's patterns", "Biological strategies", "Ecosystem principles"],
        }
        actions = technique_actions.get(technique, ["Combine", "Adapt", "Modify"])
        ideas = []
        for i in range(min(num_ideas, len(actions))):
            action = actions[i]
            ideas.append(
                {
                    "id": f"idea_{i + 1}",
                    "technique": technique,
                    "action": action,
                    "description": f"Apply '{action}' to: {problem_statement[:100]}",
                    "domain": domain,
                    "feasibility": 0.7 - i * 0.05,
                    "novelty": 0.8 - i * 0.08,
                }
            )
        return {
            "problem_statement": problem_statement,
            "domain": domain,
            "technique": technique,
            "constraints": constraints or {},
            "ideas": ideas,
            "total_generated": len(ideas),
            "generated_at": datetime.now(UTC).isoformat(),
        }


class CrossDomainCreativeIntegrator:
    """Integrator for synthesizing concepts across multiple domains."""

    async def generate_cross_domain_synthesis(
        self,
        *,
        session: Session,
        agent_id: str,
        primary_domain: str,
        secondary_domains: list[str],
        synthesis_goal: str,
    ) -> dict[str, Any]:
        """Synthesize concepts from multiple domains to create novel outputs."""
        all_domains = [primary_domain] + secondary_domains
        connections: list[dict[str, Any]] = []
        for secondary in secondary_domains:
            connections.append(
                {
                    "primary_domain": primary_domain,
                    "secondary_domain": secondary,
                    "connection_type": "analogical",
                    "strength": 0.7,
                    "description": f"Bridge concepts from {primary_domain} and {secondary}",
                }
            )
        synthesis_id = f"synth_{uuid4().hex[:8]}"
        return {
            "synthesis_id": synthesis_id,
            "agent_id": agent_id,
            "domains": all_domains,
            "synthesis_goal": synthesis_goal,
            "connections": connections,
            "novelty_score": 0.75,
            "coherence_score": 0.68,
            "potential_applications": [
                f"Apply {primary_domain} principles to {secondary_domains[0] if secondary_domains else 'other domains'}",
                f"Cross-pollinate methods between {', '.join(all_domains)}",
            ],
            "generated_at": datetime.now(UTC).isoformat(),
        }
