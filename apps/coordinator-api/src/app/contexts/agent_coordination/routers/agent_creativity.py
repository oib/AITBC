"""
Agent Creativity API Endpoints
REST API for agent creativity enhancement, ideation, and cross-domain synthesis
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlmodel import select

from aitbc.aitbc_logging import get_logger

from ..domain.agent_performance import CreativeCapability
from ....storage import get_session
from ..services.creative_capabilities_service import (
    CreativityEnhancementEngine,
    CrossDomainCreativeIntegrator,
    IdeationAlgorithm,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/agent-creativity", tags=["agent-creativity"])


class CreativeCapabilityCreate(BaseModel):
    agent_id: str
    creative_domain: str = Field(..., description="e.g., artistic, design, innovation, scientific, narrative")
    capability_type: str = Field(..., description="e.g., generative, compositional, analytical, innovative")
    generation_models: list[str]
    initial_score: float = Field(0.5, ge=0.0, le=1.0)


class CreativeCapabilityResponse(BaseModel):
    capability_id: str
    agent_id: str
    creative_domain: str
    capability_type: str
    originality_score: float
    novelty_score: float
    aesthetic_quality: float
    coherence_score: float
    style_variety: int
    creative_specializations: list[str]
    status: str


class EnhanceCreativityRequest(BaseModel):
    algorithm: str = Field(
        "divergent_thinking",
        description="divergent_thinking, conceptual_blending, morphological_analysis, lateral_thinking, bisociation",
    )
    training_cycles: int = Field(100, ge=1, le=1000)


class EvaluateCreationRequest(BaseModel):
    creation_data: dict[str, Any]
    expert_feedback: dict[str, float] | None = None


class IdeationRequest(BaseModel):
    problem_statement: str
    domain: str
    technique: str = Field("scamper", description="scamper, triz, six_thinking_hats, first_principles, biomimicry")
    num_ideas: int = Field(5, ge=1, le=20)
    constraints: dict[str, Any] | None = None


class SynthesisRequest(BaseModel):
    agent_id: str
    primary_domain: str
    secondary_domains: list[str]
    synthesis_goal: str


@router.post("/capabilities", response_model=CreativeCapabilityResponse)
async def create_creative_capability(
    request: CreativeCapabilityCreate, session: Annotated[Session, Depends(get_session)]
) -> CreativeCapabilityResponse:
    """Initialize a new creative capability for an agent"""
    engine = CreativityEnhancementEngine()
    try:
        capability = await engine.create_creative_capability(
            session=session,
            agent_id=request.agent_id,
            creative_domain=request.creative_domain,
            capability_type=request.capability_type,
            generation_models=request.generation_models,
            initial_score=request.initial_score,
        )  # type: ignore[attr-defined]
        return capability  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error creating creative capability: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/capabilities/{capability_id}/enhance")
async def enhance_creativity(
    capability_id: str, request: EnhanceCreativityRequest, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Enhance a specific creative capability using specified algorithm"""
    engine = CreativityEnhancementEngine()
    try:
        result = await engine.enhance_creativity(
            session=session, capability_id=capability_id, algorithm=request.algorithm, training_cycles=request.training_cycles
        )  # type: ignore[attr-defined]
        return result  # type: ignore[no-any-return]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Error enhancing creativity: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/capabilities/{capability_id}/evaluate")
async def evaluate_creation(
    capability_id: str, request: EvaluateCreationRequest, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Evaluate a creative output and update agent capability metrics"""
    engine = CreativityEnhancementEngine()
    try:
        result = await engine.evaluate_creation(
            session=session,
            capability_id=capability_id,
            creation_data=request.creation_data,
            expert_feedback=request.expert_feedback,
        )  # type: ignore[attr-defined]
        return result  # type: ignore[no-any-return]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Error evaluating creation: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ideation/generate")
async def generate_ideas(request: IdeationRequest) -> dict[str, Any]:
    """Generate innovative ideas using specialized ideation algorithms"""
    ideation_engine = IdeationAlgorithm()
    try:
        result = await ideation_engine.generate_ideas(
            problem_statement=request.problem_statement,
            domain=request.domain,
            technique=request.technique,
            num_ideas=request.num_ideas,
            constraints=request.constraints,
        )  # type: ignore[attr-defined]
        return result  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error generating ideas: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/synthesis/cross-domain")
async def synthesize_cross_domain(
    request: SynthesisRequest, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Synthesize concepts from multiple domains to create novel outputs"""
    integrator = CrossDomainCreativeIntegrator()
    try:
        result = await integrator.generate_cross_domain_synthesis(
            session=session,
            agent_id=request.agent_id,
            primary_domain=request.primary_domain,
            secondary_domains=request.secondary_domains,
            synthesis_goal=request.synthesis_goal,
        )  # type: ignore[attr-defined]
        return result  # type: ignore[no-any-return]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error in cross-domain synthesis: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/capabilities/{agent_id}")
async def list_agent_creative_capabilities(
    agent_id: str, session: Annotated[Session, Depends(get_session)]
) -> list[CreativeCapability]:
    """List all creative capabilities for a specific agent"""
    try:
        capabilities = session.execute(select(CreativeCapability).where(CreativeCapability.agent_id == agent_id)).all()
        return capabilities  # type: ignore[return-value]
    except Exception as e:
        logger.error("Error fetching creative capabilities: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
