from sqlalchemy.orm import Session
from typing import Annotated
"""
Agent Creativity API Endpoints
REST API for agent creativity enhancement, ideation, and cross-domain synthesis
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field
from aitbc.logging import get_logger

from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..services.creative_capabilities_service import (
    CreativityEnhancementEngine, IdeationAlgorithm, CrossDomainCreativeIntegrator
)
from ..domain.agent_performance import CreativeCapability

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/agent-creativity", tags=["agent-creativity"])

# Models
class CreativeCapabilityCreate(BaseModel):
    agent_id: str
    creative_domain: str = Field(..., description="e.g., artistic, design, innovation, scientific, narrative")
    capability_type: str = Field(..., description="e.g., generative, compositional, analytical, innovative")
    generation_models: List[str]
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
    creative_specializations: List[str]
    status: str

class EnhanceCreativityRequest(BaseModel):
    algorithm: str = Field("divergent_thinking", description="divergent_thinking, conceptual_blending, morphological_analysis, lateral_thinking, bisociation")
    training_cycles: int = Field(100, ge=1, le=1000)

class EvaluateCreationRequest(BaseModel):
    creation_data: Dict[str, Any]
    expert_feedback: Optional[Dict[str, float]] = None

class IdeationRequest(BaseModel):
    problem_statement: str
    domain: str
    technique: str = Field("scamper", description="scamper, triz, six_thinking_hats, first_principles, biomimicry")
    num_ideas: int = Field(5, ge=1, le=20)
    constraints: Optional[Dict[str, Any]] = None

class SynthesisRequest(BaseModel):
    agent_id: str
    primary_domain: str
    secondary_domains: List[str]
    synthesis_goal: str

# Endpoints

@router.post("/capabilities", response_model=CreativeCapabilityResponse)
async def create_creative_capability(
    request: CreativeCapabilityCreate,
    session: Annotated[Session, Depends(get_session)] = Depends()
):
    """Initialize a new creative capability for an agent"""
    engine = CreativityEnhancementEngine()
    
    try:
        capability = await engine.create_creative_capability(
            session=session,
            agent_id=request.agent_id,
            creative_domain=request.creative_domain,
            capability_type=request.capability_type,
            generation_models=request.generation_models,
            initial_score=request.initial_score
        )
        
        return capability
    except Exception as e:
        logger.error(f"Error creating creative capability: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/capabilities/{capability_id}/enhance")
async def enhance_creativity(
    capability_id: str,
    request: EnhanceCreativityRequest,
    session: Annotated[Session, Depends(get_session)] = Depends()
):
    """Enhance a specific creative capability using specified algorithm"""
    engine = CreativityEnhancementEngine()
    
    try:
        result = await engine.enhance_creativity(
            session=session,
            capability_id=capability_id,
            algorithm=request.algorithm,
            training_cycles=request.training_cycles
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error enhancing creativity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/capabilities/{capability_id}/evaluate")
async def evaluate_creation(
    capability_id: str,
    request: EvaluateCreationRequest,
    session: Annotated[Session, Depends(get_session)] = Depends()
):
    """Evaluate a creative output and update agent capability metrics"""
    engine = CreativityEnhancementEngine()
    
    try:
        result = await engine.evaluate_creation(
            session=session,
            capability_id=capability_id,
            creation_data=request.creation_data,
            expert_feedback=request.expert_feedback
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error evaluating creation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ideation/generate")
async def generate_ideas(request: IdeationRequest):
    """Generate innovative ideas using specialized ideation algorithms"""
    ideation_engine = IdeationAlgorithm()
    
    try:
        result = await ideation_engine.generate_ideas(
            problem_statement=request.problem_statement,
            domain=request.domain,
            technique=request.technique,
            num_ideas=request.num_ideas,
            constraints=request.constraints
        )
        return result
    except Exception as e:
        logger.error(f"Error generating ideas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/synthesis/cross-domain")
async def synthesize_cross_domain(
    request: SynthesisRequest,
    session: Annotated[Session, Depends(get_session)] = Depends()
):
    """Synthesize concepts from multiple domains to create novel outputs"""
    integrator = CrossDomainCreativeIntegrator()
    
    try:
        result = await integrator.generate_cross_domain_synthesis(
            session=session,
            agent_id=request.agent_id,
            primary_domain=request.primary_domain,
            secondary_domains=request.secondary_domains,
            synthesis_goal=request.synthesis_goal
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in cross-domain synthesis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/capabilities/{agent_id}")
async def list_agent_creative_capabilities(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends()
):
    """List all creative capabilities for a specific agent"""
    try:
        capabilities = session.execute(
            select(CreativeCapability).where(CreativeCapability.agent_id == agent_id)
        ).all()
        
        return capabilities
    except Exception as e:
        logger.error(f"Error fetching creative capabilities: {e}")
        raise HTTPException(status_code=500, detail=str(e))
