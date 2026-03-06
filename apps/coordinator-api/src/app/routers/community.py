"""
Community and Developer Ecosystem API Endpoints
REST API for managing OpenClaw developer profiles, SDKs, solutions, and hackathons
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field
from aitbc.logging import get_logger

from ..storage import SessionDep
from ..services.community_service import (
    DeveloperEcosystemService, ThirdPartySolutionService,
    InnovationLabService, CommunityPlatformService
)
from ..domain.community import (
    DeveloperProfile, AgentSolution, InnovationLab, 
    CommunityPost, Hackathon, DeveloperTier, SolutionStatus, LabStatus
)

logger = get_logger(__name__)

router = APIRouter(prefix="/community", tags=["community"])

# Models
class DeveloperProfileCreate(BaseModel):
    user_id: str
    username: str
    bio: Optional[str] = None
    skills: List[str] = Field(default_factory=list)

class SolutionPublishRequest(BaseModel):
    developer_id: str
    title: str
    description: str
    version: str = "1.0.0"
    capabilities: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    price_model: str = "free"
    price_amount: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

class LabProposalRequest(BaseModel):
    title: str
    description: str
    research_area: str
    funding_goal: float = 0.0
    milestones: List[Dict[str, Any]] = Field(default_factory=list)

class PostCreateRequest(BaseModel):
    title: str
    content: str
    category: str = "discussion"
    tags: List[str] = Field(default_factory=list)
    parent_post_id: Optional[str] = None

class HackathonCreateRequest(BaseModel):
    title: str
    description: str
    theme: str
    sponsor: str = "AITBC Foundation"
    prize_pool: float = 0.0
    registration_start: str
    registration_end: str
    event_start: str
    event_end: str

# Endpoints - Developer Ecosystem
@router.post("/developers", response_model=DeveloperProfile)
async def create_developer_profile(request: DeveloperProfileCreate, session: SessionDep):
    """Register a new developer in the OpenClaw ecosystem"""
    service = DeveloperEcosystemService(session)
    try:
        profile = await service.create_developer_profile(
            user_id=request.user_id,
            username=request.username,
            bio=request.bio,
            skills=request.skills
        )
        return profile
    except Exception as e:
        logger.error(f"Error creating developer profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/developers/{developer_id}", response_model=DeveloperProfile)
async def get_developer_profile(developer_id: str, session: SessionDep):
    """Get a developer's profile and reputation"""
    service = DeveloperEcosystemService(session)
    profile = await service.get_developer_profile(developer_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Developer not found")
    return profile

@router.get("/sdk/latest")
async def get_latest_sdk(session: SessionDep):
    """Get information about the latest OpenClaw SDK releases"""
    service = DeveloperEcosystemService(session)
    return await service.get_sdk_release_info()

# Endpoints - Marketplace Solutions
@router.post("/solutions/publish", response_model=AgentSolution)
async def publish_solution(request: SolutionPublishRequest, session: SessionDep):
    """Publish a new third-party agent solution to the marketplace"""
    service = ThirdPartySolutionService(session)
    try:
        solution = await service.publish_solution(request.developer_id, request.dict(exclude={'developer_id'}))
        return solution
    except Exception as e:
        logger.error(f"Error publishing solution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/solutions", response_model=List[AgentSolution])
async def list_solutions(
    category: Optional[str] = None, 
    limit: int = 50,
):
    """List available third-party agent solutions"""
    service = ThirdPartySolutionService(session)
    return await service.list_published_solutions(category, limit)

@router.post("/solutions/{solution_id}/purchase")
async def purchase_solution(solution_id: str, session: SessionDep, buyer_id: str = Body(embed=True)):
    """Purchase or install a third-party solution"""
    service = ThirdPartySolutionService(session)
    try:
        result = await service.purchase_solution(buyer_id, solution_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoints - Innovation Labs
@router.post("/labs/propose", response_model=InnovationLab)
async def propose_innovation_lab(
    researcher_id: str = Query(...), 
    request: LabProposalRequest = Body(...), 
):
    """Propose a new agent innovation lab or research program"""
    service = InnovationLabService(session)
    try:
        lab = await service.propose_lab(researcher_id, request.dict())
        return lab
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/labs/{lab_id}/join")
async def join_innovation_lab(lab_id: str, session: SessionDep, developer_id: str = Body(embed=True)):
    """Join an active innovation lab"""
    service = InnovationLabService(session)
    try:
        lab = await service.join_lab(lab_id, developer_id)
        return lab
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/labs/{lab_id}/fund")
async def fund_innovation_lab(lab_id: str, session: SessionDep, amount: float = Body(embed=True)):
    """Provide funding to a proposed innovation lab"""
    service = InnovationLabService(session)
    try:
        lab = await service.fund_lab(lab_id, amount)
        return lab
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Endpoints - Community Platform
@router.post("/platform/posts", response_model=CommunityPost)
async def create_community_post(
    author_id: str = Query(...),
    request: PostCreateRequest = Body(...),
):
    """Create a new post in the community forum"""
    service = CommunityPlatformService(session)
    try:
        post = await service.create_post(author_id, request.dict())
        return post
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/platform/feed", response_model=List[CommunityPost])
async def get_community_feed(
    category: Optional[str] = None,
    limit: int = 20,
):
    """Get the latest community posts and discussions"""
    service = CommunityPlatformService(session)
    return await service.get_feed(category, limit)

@router.post("/platform/posts/{post_id}/upvote")
async def upvote_community_post(post_id: str, session: SessionDep):
    """Upvote a community post (rewards author reputation)"""
    service = CommunityPlatformService(session)
    try:
        post = await service.upvote_post(post_id)
        return post
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Endpoints - Hackathons
@router.post("/hackathons/create", response_model=Hackathon)
async def create_hackathon(
    organizer_id: str = Query(...),
    request: HackathonCreateRequest = Body(...),
):
    """Create a new agent innovation hackathon (requires high reputation)"""
    service = CommunityPlatformService(session)
    try:
        hackathon = await service.create_hackathon(organizer_id, request.dict())
        return hackathon
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hackathons/{hackathon_id}/register")
async def register_for_hackathon(hackathon_id: str, session: SessionDep, developer_id: str = Body(embed=True)):
    """Register for an upcoming or ongoing hackathon"""
    service = CommunityPlatformService(session)
    try:
        hackathon = await service.register_for_hackathon(hackathon_id, developer_id)
        return hackathon
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
