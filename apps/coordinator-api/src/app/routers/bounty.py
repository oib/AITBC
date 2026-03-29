from typing import Annotated
"""
Bounty Management API
REST API for AI agent bounty system with ZK-proof verification
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator

from ..storage import get_session
from ..logging import get_logger
from ..domain.bounty import (
    Bounty, BountySubmission, BountyStatus, BountyTier, 
    SubmissionStatus, BountyStats, BountyIntegration
)
from ..services.bounty_service import BountyService
from ..services.blockchain_service import BlockchainService
from ..auth import get_current_user


router = APIRouter()

# Pydantic models for request/response
class BountyCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10, max_length=5000)
    reward_amount: float = Field(..., gt=0)
    tier: BountyTier = Field(default=BountyTier.BRONZE)
    performance_criteria: Dict[str, Any] = Field(default_factory=dict)
    min_accuracy: float = Field(default=90.0, ge=0, le=100)
    max_response_time: Optional[int] = Field(default=None, gt=0)
    deadline: datetime = Field(..., gt=datetime.utcnow())
    max_submissions: int = Field(default=100, gt=0, le=1000)
    requires_zk_proof: bool = Field(default=True)
    auto_verify_threshold: float = Field(default=95.0, ge=0, le=100)
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = Field(default=None)
    difficulty: Optional[str] = Field(default=None)

    @validator('deadline')
    def validate_deadline(cls, v):
        if v <= datetime.utcnow():
            raise ValueError('Deadline must be in the future')
        if v > datetime.utcnow() + timedelta(days=365):
            raise ValueError('Deadline cannot be more than 1 year in the future')
        return v

    @validator('reward_amount')
    def validate_reward_amount(cls, v, values):
        tier = values.get('tier', BountyTier.BRONZE)
        tier_minimums = {
            BountyTier.BRONZE: 100.0,
            BountyTier.SILVER: 500.0,
            BountyTier.GOLD: 1000.0,
            BountyTier.PLATINUM: 5000.0
        }
        if v < tier_minimums.get(tier, 100.0):
            raise ValueError(f'Reward amount must be at least {tier_minimums[tier]} for {tier} tier')
        return v

class BountyResponse(BaseModel):
    bounty_id: str
    title: str
    description: str
    reward_amount: float
    creator_id: str
    tier: BountyTier
    status: BountyStatus
    performance_criteria: Dict[str, Any]
    min_accuracy: float
    max_response_time: Optional[int]
    deadline: datetime
    creation_time: datetime
    max_submissions: int
    submission_count: int
    requires_zk_proof: bool
    auto_verify_threshold: float
    winning_submission_id: Optional[str]
    winner_address: Optional[str]
    creation_fee: float
    success_fee: float
    platform_fee: float
    tags: List[str]
    category: Optional[str]
    difficulty: Optional[str]

class BountySubmissionRequest(BaseModel):
    bounty_id: str
    zk_proof: Optional[Dict[str, Any]] = Field(default=None)
    performance_hash: str = Field(..., min_length=1)
    accuracy: float = Field(..., ge=0, le=100)
    response_time: Optional[int] = Field(default=None, gt=0)
    compute_power: Optional[float] = Field(default=None, gt=0)
    energy_efficiency: Optional[float] = Field(default=None, ge=0, le=100)
    submission_data: Dict[str, Any] = Field(default_factory=dict)
    test_results: Dict[str, Any] = Field(default_factory=dict)

class BountySubmissionResponse(BaseModel):
    submission_id: str
    bounty_id: str
    submitter_address: str
    accuracy: float
    response_time: Optional[int]
    compute_power: Optional[float]
    energy_efficiency: Optional[float]
    zk_proof: Optional[Dict[str, Any]]
    performance_hash: str
    status: SubmissionStatus
    verification_time: Optional[datetime]
    verifier_address: Optional[str]
    dispute_reason: Optional[str]
    dispute_time: Optional[datetime]
    dispute_resolved: bool
    submission_time: datetime
    submission_data: Dict[str, Any]
    test_results: Dict[str, Any]

class BountyVerificationRequest(BaseModel):
    bounty_id: str
    submission_id: str
    verified: bool
    verifier_address: str
    verification_notes: Optional[str] = Field(default=None)

class BountyDisputeRequest(BaseModel):
    bounty_id: str
    submission_id: str
    dispute_reason: str = Field(..., min_length=10, max_length=1000)

class BountyFilterRequest(BaseModel):
    status: Optional[BountyStatus] = None
    tier: Optional[BountyTier] = None
    creator_id: Optional[str] = None
    category: Optional[str] = None
    min_reward: Optional[float] = Field(default=None, ge=0)
    max_reward: Optional[float] = Field(default=None, ge=0)
    deadline_before: Optional[datetime] = None
    deadline_after: Optional[datetime] = None
    tags: Optional[List[str]] = None
    requires_zk_proof: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

class BountyStatsResponse(BaseModel):
    total_bounties: int
    active_bounties: int
    completed_bounties: int
    expired_bounties: int
    disputed_bounties: int
    total_value_locked: float
    total_rewards_paid: float
    total_fees_collected: float
    average_reward: float
    success_rate: float
    average_completion_time: Optional[float]
    average_accuracy: Optional[float]
    unique_creators: int
    unique_submitters: int
    total_submissions: int
    tier_distribution: Dict[str, int]

# Dependency injection
def get_bounty_service(session: Annotated[Session, Depends(get_session)]) -> BountyService:
    return BountyService(session)

def get_blockchain_service() -> BlockchainService:
    return BlockchainService()

# API endpoints
@router.post("/bounties", response_model=BountyResponse)
async def create_bounty(
    request: BountyCreateRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Create a new bounty"""
    try:
        logger.info(f"Creating bounty: {request.title} by user {current_user['address']}")
        
        # Create bounty in database
        bounty = await bounty_service.create_bounty(
            creator_id=current_user['address'],
            **request.dict()
        )
        
        # Deploy bounty contract in background
        background_tasks.add_task(
            blockchain_service.deploy_bounty_contract,
            bounty.bounty_id,
            bounty.reward_amount,
            bounty.tier,
            bounty.deadline
        )
        
        return BountyResponse.from_orm(bounty)
        
    except Exception as e:
        logger.error(f"Failed to create bounty: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties", response_model=List[BountyResponse])
async def get_bounties(
    filters: BountyFilterRequest = Depends(),
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service)
):
    """Get filtered list of bounties"""
    try:
        bounties = await bounty_service.get_bounties(
            status=filters.status,
            tier=filters.tier,
            creator_id=filters.creator_id,
            category=filters.category,
            min_reward=filters.min_reward,
            max_reward=filters.max_reward,
            deadline_before=filters.deadline_before,
            deadline_after=filters.deadline_after,
            tags=filters.tags,
            requires_zk_proof=filters.requires_zk_proof,
            page=filters.page,
            limit=filters.limit
        )
        
        return [BountyResponse.from_orm(bounty) for bounty in bounties]
        
    except Exception as e:
        logger.error(f"Failed to get bounties: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/{bounty_id}", response_model=BountyResponse)
async def get_bounty(
    bounty_id: str,
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service)
):
    """Get bounty details"""
    try:
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        
        return BountyResponse.from_orm(bounty)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get bounty {bounty_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bounties/{bounty_id}/submit", response_model=BountySubmissionResponse)
async def submit_bounty_solution(
    bounty_id: str,
    request: BountySubmissionRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Submit a solution to a bounty"""
    try:
        logger.info(f"Submitting solution for bounty {bounty_id} by {current_user['address']}")
        
        # Validate bounty exists and is active
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        
        if bounty.status != BountyStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Bounty is not active")
        
        if datetime.utcnow() > bounty.deadline:
            raise HTTPException(status_code=400, detail="Bounty deadline has passed")
        
        # Create submission
        submission = await bounty_service.create_submission(
            bounty_id=bounty_id,
            submitter_address=current_user['address'],
            **request.dict()
        )
        
        # Submit to blockchain in background
        background_tasks.add_task(
            blockchain_service.submit_bounty_solution,
            bounty_id,
            submission.submission_id,
            request.zk_proof,
            request.performance_hash,
            request.accuracy,
            request.response_time
        )
        
        return BountySubmissionResponse.from_orm(submission)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit bounty solution: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/{bounty_id}/submissions", response_model=List[BountySubmissionResponse])
async def get_bounty_submissions(
    bounty_id: str,
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    current_user: dict = Depends(get_current_user)
):
    """Get all submissions for a bounty"""
    try:
        # Check if user is bounty creator or has permission
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        
        if bounty.creator_id != current_user['address']:
            # Check if user has admin permissions
            if not current_user.get('is_admin', False):
                raise HTTPException(status_code=403, detail="Not authorized to view submissions")
        
        submissions = await bounty_service.get_bounty_submissions(bounty_id)
        return [BountySubmissionResponse.from_orm(sub) for sub in submissions]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get bounty submissions: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bounties/{bounty_id}/verify")
async def verify_bounty_submission(
    bounty_id: str,
    request: BountyVerificationRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Verify a bounty submission (oracle/admin only)"""
    try:
        # Check permissions
        if not current_user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Not authorized to verify submissions")
        
        # Verify submission
        await bounty_service.verify_submission(
            bounty_id=bounty_id,
            submission_id=request.submission_id,
            verified=request.verified,
            verifier_address=request.verifier_address,
            verification_notes=request.verification_notes
        )
        
        # Update blockchain in background
        background_tasks.add_task(
            blockchain_service.verify_submission,
            bounty_id,
            request.submission_id,
            request.verified,
            request.verifier_address
        )
        
        return {"message": "Submission verified successfully"}
        
    except Exception as e:
        logger.error(f"Failed to verify bounty submission: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bounties/{bounty_id}/dispute")
async def dispute_bounty_submission(
    bounty_id: str,
    request: BountyDisputeRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Dispute a bounty submission"""
    try:
        # Create dispute
        await bounty_service.create_dispute(
            bounty_id=bounty_id,
            submission_id=request.submission_id,
            disputer_address=current_user['address'],
            dispute_reason=request.dispute_reason
        )
        
        # Handle dispute on blockchain in background
        background_tasks.add_task(
            blockchain_service.dispute_submission,
            bounty_id,
            request.submission_id,
            current_user['address'],
            request.dispute_reason
        )
        
        return {"message": "Dispute created successfully"}
        
    except Exception as e:
        logger.error(f"Failed to create dispute: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/my/created", response_model=List[BountyResponse])
async def get_my_created_bounties(
    status: Optional[BountyStatus] = None,
    page: int = Field(default=1, ge=1),
    limit: int = Field(default=20, ge=1, le=100),
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    current_user: dict = Depends(get_current_user)
):
    """Get bounties created by the current user"""
    try:
        bounties = await bounty_service.get_user_created_bounties(
            user_address=current_user['address'],
            status=status,
            page=page,
            limit=limit
        )
        
        return [BountyResponse.from_orm(bounty) for bounty in bounties]
        
    except Exception as e:
        logger.error(f"Failed to get user created bounties: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/my/submissions", response_model=List[BountySubmissionResponse])
async def get_my_submissions(
    status: Optional[SubmissionStatus] = None,
    page: int = Field(default=1, ge=1),
    limit: int = Field(default=20, ge=1, le=100),
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    current_user: dict = Depends(get_current_user)
):
    """Get submissions made by the current user"""
    try:
        submissions = await bounty_service.get_user_submissions(
            user_address=current_user['address'],
            status=status,
            page=page,
            limit=limit
        )
        
        return [BountySubmissionResponse.from_orm(sub) for sub in submissions]
        
    except Exception as e:
        logger.error(f"Failed to get user submissions: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/leaderboard")
async def get_bounty_leaderboard(
    period: str = Field(default="weekly", regex="^(daily|weekly|monthly)$"),
    limit: int = Field(default=50, ge=1, le=100),
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service)
):
    """Get bounty leaderboard"""
    try:
        leaderboard = await bounty_service.get_leaderboard(
            period=period,
            limit=limit
        )
        
        return leaderboard
        
    except Exception as e:
        logger.error(f"Failed to get bounty leaderboard: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/stats", response_model=BountyStatsResponse)
async def get_bounty_stats(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service)
):
    """Get bounty statistics"""
    try:
        stats = await bounty_service.get_bounty_stats(period=period)
        
        return BountyStatsResponse.from_orm(stats)
        
    except Exception as e:
        logger.error(f"Failed to get bounty stats: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bounties/{bounty_id}/expire")
async def expire_bounty(
    bounty_id: str,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Expire a bounty (creator only)"""
    try:
        # Check if user is bounty creator
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        
        if bounty.creator_id != current_user['address']:
            raise HTTPException(status_code=403, detail="Not authorized to expire bounty")
        
        if bounty.status != BountyStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Bounty is not active")
        
        if datetime.utcnow() <= bounty.deadline:
            raise HTTPException(status_code=400, detail="Bounty deadline has not passed")
        
        # Expire bounty
        await bounty_service.expire_bounty(bounty_id)
        
        # Handle on blockchain in background
        background_tasks.add_task(
            blockchain_service.expire_bounty,
            bounty_id
        )
        
        return {"message": "Bounty expired successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to expire bounty: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/categories")
async def get_bounty_categories(
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service)
):
    """Get all bounty categories"""
    try:
        categories = await bounty_service.get_categories()
        return {"categories": categories}
        
    except Exception as e:
        logger.error(f"Failed to get bounty categories: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/tags")
async def get_bounty_tags(
    limit: int = Field(default=100, ge=1, le=500),
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service)
):
    """Get popular bounty tags"""
    try:
        tags = await bounty_service.get_popular_tags(limit=limit)
        return {"tags": tags}
        
    except Exception as e:
        logger.error(f"Failed to get bounty tags: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bounties/search")
async def search_bounties(
    query: str = Field(..., min_length=1, max_length=100),
    page: int = Field(default=1, ge=1),
    limit: int = Field(default=20, ge=1, le=100),
    session: Annotated[Session, Depends(get_session)],
    bounty_service: BountyService = Depends(get_bounty_service)
):
    """Search bounties by text"""
    try:
        bounties = await bounty_service.search_bounties(
            query=query,
            page=page,
            limit=limit
        )
        
        return [BountyResponse.from_orm(bounty) for bounty in bounties]
        
    except Exception as e:
        logger.error(f"Failed to search bounties: {e}")
        raise HTTPException(status_code=400, detail=str(e))
