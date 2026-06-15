"""
Bounty Management API
REST API for AI agent bounty system with ZK-proof verification
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)
from ....domain.bounty import BountyStatus, BountyTier, SubmissionStatus
from ....routers.users import get_current_user
from ....services.bounty_service import BountyService
from ....storage import get_session
from ...blockchain.services.blockchain import BlockchainService

router = APIRouter()


class BountyCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10, max_length=5000)
    reward_amount: float = Field(..., gt=0)
    tier: BountyTier = Field(default=BountyTier.BRONZE)
    performance_criteria: dict[str, Any] = Field(default_factory=dict)
    min_accuracy: float = Field(default=90.0, ge=0, le=100)
    max_response_time: int | None = Field(default=None, gt=0)
    deadline: datetime = Field(..., gt=datetime.now(UTC))
    max_submissions: int = Field(default=100, gt=0, le=1000)
    requires_zk_proof: bool = Field(default=True)
    auto_verify_threshold: float = Field(default=95.0, ge=0, le=100)
    tags: list[str] = Field(default_factory=list)
    category: str | None = Field(default=None)
    difficulty: str | None = Field(default=None)

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, v: datetime) -> datetime:
        if v <= datetime.now(UTC):
            raise ValueError("Deadline must be in the future")
        if v > datetime.now(UTC) + timedelta(days=365):
            raise ValueError("Deadline cannot be more than 1 year in the future")
        return v

    @model_validator(mode="after")
    def validate_reward_amount(self) -> "BountyCreateRequest":
        tier_minimums = {
            BountyTier.BRONZE: 100.0,
            BountyTier.SILVER: 500.0,
            BountyTier.GOLD: 1000.0,
            BountyTier.PLATINUM: 5000.0,
        }
        if self.reward_amount < tier_minimums.get(self.tier, 100.0):
            raise ValueError(f"Reward amount must be at least {tier_minimums[self.tier]} for {self.tier} tier")
        return self


class BountyResponse(BaseModel):
    bounty_id: str
    title: str
    description: str
    reward_amount: float
    creator_id: str
    tier: BountyTier
    status: BountyStatus
    performance_criteria: dict[str, Any]
    min_accuracy: float
    max_response_time: int | None
    deadline: datetime
    creation_time: datetime
    max_submissions: int
    submission_count: int
    requires_zk_proof: bool
    auto_verify_threshold: float
    winning_submission_id: str | None
    winner_address: str | None
    creation_fee: float
    success_fee: float
    platform_fee: float
    tags: list[str]
    category: str | None
    difficulty: str | None


class BountySubmissionRequest(BaseModel):
    bounty_id: str
    zk_proof: dict[str, Any] | None = Field(default=None)
    performance_hash: str = Field(..., min_length=1)
    accuracy: float = Field(..., ge=0, le=100)
    response_time: int | None = Field(default=None, gt=0)
    compute_power: float | None = Field(default=None, gt=0)
    energy_efficiency: float | None = Field(default=None, ge=0, le=100)
    submission_data: dict[str, Any] = Field(default_factory=dict)
    test_results: dict[str, Any] = Field(default_factory=dict)


class BountySubmissionResponse(BaseModel):
    submission_id: str
    bounty_id: str
    submitter_address: str
    accuracy: float
    response_time: int | None
    compute_power: float | None
    energy_efficiency: float | None
    zk_proof: dict[str, Any] | None
    performance_hash: str
    status: SubmissionStatus
    verification_time: datetime | None
    verifier_address: str | None
    dispute_reason: str | None
    dispute_time: datetime | None
    dispute_resolved: bool
    submission_time: datetime
    submission_data: dict[str, Any]
    test_results: dict[str, Any]


class BountyVerificationRequest(BaseModel):
    bounty_id: str
    submission_id: str
    verified: bool
    verifier_address: str
    verification_notes: str | None = Field(default=None)


class BountyDisputeRequest(BaseModel):
    bounty_id: str
    submission_id: str
    dispute_reason: str = Field(..., min_length=10, max_length=1000)


class BountyFilterRequest(BaseModel):
    status: BountyStatus | None = None
    tier: BountyTier | None = None
    creator_id: str | None = None
    category: str | None = None
    min_reward: float | None = Field(default=None, ge=0)
    max_reward: float | None = Field(default=None, ge=0)
    deadline_before: datetime | None = None
    deadline_after: datetime | None = None
    tags: list[str] | None = None
    requires_zk_proof: bool | None = None
    page: int = Query(default=1, ge=1)
    limit: int = Query(default=20, ge=1, le=100)


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
    average_completion_time: float | None
    average_accuracy: float | None
    unique_creators: int
    unique_submitters: int
    total_submissions: int
    tier_distribution: dict[str, int]


def get_bounty_service(session: Session = Depends(get_session)) -> BountyService:
    return BountyService(session)


def get_blockchain_service() -> BlockchainService:
    return BlockchainService()


@router.post("/bounties", response_model=BountyResponse)
@rate_limit(rate=20, per=60)
async def create_bounty(
    request: Request,
    bounty_request: BountyCreateRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user),
) -> BountyResponse:
    """Create a new bounty"""
    try:
        logger.info("Creating bounty: %s by user %s", request.title, current_user["address"])  # type: ignore[attr-defined]
        bounty = await bounty_service.create_bounty(creator_id=current_user["address"], **request.dict())  # type: ignore[attr-defined]
        background_tasks.add_task(
            blockchain_service.deploy_bounty_contract, bounty.bounty_id, bounty.reward_amount, bounty.tier, bounty.deadline
        )  # type: ignore[attr-defined]
        return BountyResponse.from_orm(bounty)  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to create bounty: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties", response_model=list[BountyResponse])
@rate_limit(rate=200, per=60)
async def get_bounties(
    request: Request,
    session: Session = Depends(get_session),
    filters: BountyFilterRequest = Depends(),
    bounty_service: BountyService = Depends(get_bounty_service),
) -> list[BountyResponse]:
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
            limit=filters.limit,
        )
        return [BountyResponse.from_orm(bounty) for bounty in bounties]  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to get bounties: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/{bounty_id}", response_model=BountyResponse)
@rate_limit(rate=200, per=60)
async def get_bounty(
    request: Request,
    bounty_id: str,
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
) -> BountyResponse:
    """Get bounty details"""
    try:
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        return BountyResponse.from_orm(bounty)  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get bounty %s: %s", bounty_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bounties/{bounty_id}/submit", response_model=BountySubmissionResponse)
@rate_limit(rate=20, per=60)
async def submit_bounty_solution(
    request: Request,
    bounty_id: str,
    submission_request: BountySubmissionRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user),
) -> BountySubmissionResponse:
    """Submit a solution to a bounty"""
    try:
        logger.info("Submitting solution for bounty %s by %s", bounty_id, current_user["address"])
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        if bounty.status != BountyStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Bounty is not active")
        if datetime.now(UTC) > bounty.deadline:
            raise HTTPException(status_code=400, detail="Bounty deadline has passed")
        submission = await bounty_service.create_submission(
            bounty_id=bounty_id, submitter_address=current_user["address"], **request.dict()
        )  # type: ignore[attr-defined]
        background_tasks.add_task(
            blockchain_service.submit_bounty_solution,
            bounty_id,
            submission.submission_id,
            request.zk_proof,
            request.performance_hash,
            request.accuracy,
            request.response_time,
        )  # type: ignore[attr-defined]
        return BountySubmissionResponse.from_orm(submission)  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to submit bounty solution: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/{bounty_id}/submissions", response_model=list[BountySubmissionResponse])
@rate_limit(rate=200, per=60)
async def get_bounty_submissions(
    request: Request,
    bounty_id: str,
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    current_user: dict = Depends(get_current_user),
) -> list[BountySubmissionResponse]:
    """Get all submissions for a bounty"""
    try:
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        if bounty.creator_id != current_user["address"]:
            if not current_user.get("is_admin", False):
                raise HTTPException(status_code=403, detail="Not authorized to view submissions")
        submissions = await bounty_service.get_bounty_submissions(bounty_id)
        return [BountySubmissionResponse.from_orm(sub) for sub in submissions]  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get bounty submissions: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bounties/{bounty_id}/verify")
@rate_limit(rate=20, per=60)
async def verify_bounty_submission(
    request: Request,
    bounty_id: str,
    verification_request: BountyVerificationRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Verify a bounty submission (oracle/admin only)"""
    try:
        if not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Not authorized to verify submissions")
        await bounty_service.verify_submission(
            bounty_id=bounty_id,
            submission_id=request.submission_id,
            verified=request.verified,
            verifier_address=request.verifier_address,
            verification_notes=request.verification_notes,
        )  # type: ignore[attr-defined]
        background_tasks.add_task(
            blockchain_service.verify_submission, bounty_id, request.submission_id, request.verified, request.verifier_address
        )  # type: ignore[attr-defined]
        return {"message": "Submission verified successfully"}
    except Exception as e:
        logger.error("Failed to verify bounty submission: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bounties/{bounty_id}/dispute")
@rate_limit(rate=20, per=60)
async def dispute_bounty_submission(
    request: Request,
    bounty_id: str,
    dispute_request: BountyDisputeRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Dispute a bounty submission"""
    try:
        await bounty_service.create_dispute(
            bounty_id=bounty_id,
            submission_id=request.submission_id,
            disputer_address=current_user["address"],
            dispute_reason=request.dispute_reason,
        )  # type: ignore[attr-defined]
        background_tasks.add_task(
            blockchain_service.dispute_submission,
            bounty_id,
            request.submission_id,
            current_user["address"],
            request.dispute_reason,
        )  # type: ignore[attr-defined]
        return {"message": "Dispute created successfully"}
    except Exception as e:
        logger.error("Failed to create dispute: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/my/created", response_model=list[BountyResponse])
@rate_limit(rate=200, per=60)
async def get_my_created_bounties(
    request: Request,
    status: BountyStatus | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    current_user: dict = Depends(get_current_user),
) -> list[BountyResponse]:
    """Get bounties created by the current user"""
    try:
        bounties = await bounty_service.get_user_created_bounties(
            user_address=current_user["address"], status=status, page=page, limit=limit
        )
        return [BountyResponse.from_orm(bounty) for bounty in bounties]  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to get user created bounties: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/my/submissions", response_model=list[BountySubmissionResponse])
@rate_limit(rate=200, per=60)
async def get_my_submissions(
    request: Request,
    status: SubmissionStatus | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    current_user: dict = Depends(get_current_user),
) -> list[BountySubmissionResponse]:
    """Get submissions made by the current user"""
    try:
        submissions = await bounty_service.get_user_submissions(
            user_address=current_user["address"], status=status, page=page, limit=limit
        )
        return [BountySubmissionResponse.from_orm(sub) for sub in submissions]  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to get user submissions: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/leaderboard")
@rate_limit(rate=200, per=60)
async def get_bounty_leaderboard(
    request: Request,
    period: str = Query(default="weekly", pattern="^(daily|weekly|monthly)$"),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
) -> dict[str, Any]:
    """Get bounty leaderboard"""
    try:
        leaderboard = await bounty_service.get_leaderboard(period=period, limit=limit)
        return leaderboard  # type: ignore[return-value]
    except Exception as e:
        logger.error("Failed to get bounty leaderboard: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/stats", response_model=BountyStatsResponse)
@rate_limit(rate=200, per=60)
async def get_bounty_stats(
    request: Request,
    period: str = Query(default="monthly", pattern="^(daily|weekly|monthly)$"),
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
) -> BountyStatsResponse:
    """Get bounty statistics"""
    try:
        stats = await bounty_service.get_bounty_stats(period=period)
        return BountyStatsResponse.from_orm(stats)  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to get bounty stats: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bounties/{bounty_id}/expire")
@rate_limit(rate=20, per=60)
async def expire_bounty(
    request: Request,
    bounty_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Expire a bounty (creator only)"""
    try:
        bounty = await bounty_service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        if bounty.creator_id != current_user["address"]:
            raise HTTPException(status_code=403, detail="Not authorized to expire bounty")
        if bounty.status != BountyStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Bounty is not active")
        if datetime.now(UTC) <= bounty.deadline:
            raise HTTPException(status_code=400, detail="Bounty deadline has not passed")
        await bounty_service.expire_bounty(bounty_id)
        background_tasks.add_task(blockchain_service.expire_bounty, bounty_id)  # type: ignore[attr-defined]
        return {"message": "Bounty expired successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to expire bounty: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/categories")
@rate_limit(rate=500, per=60)
async def get_bounty_categories(
    request: Request, session: Session = Depends(get_session), bounty_service: BountyService = Depends(get_bounty_service)
) -> dict[str, Any]:
    """Get all bounty categories"""
    try:
        categories = await bounty_service.get_categories()
        return {"categories": categories}
    except Exception as e:
        logger.error("Failed to get bounty categories: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/tags")
@rate_limit(rate=500, per=60)
async def get_bounty_tags(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
) -> dict[str, Any]:
    """Get popular bounty tags"""
    try:
        tags = await bounty_service.get_popular_tags(limit=limit)
        return {"tags": tags}
    except Exception as e:
        logger.error("Failed to get bounty tags: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bounties/search")
@rate_limit(rate=200, per=60)
async def search_bounties(
    request: Request,
    query: str = Query(..., min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    bounty_service: BountyService = Depends(get_bounty_service),
) -> list[BountyResponse]:
    """Search bounties by text"""
    try:
        bounties = await bounty_service.search_bounties(query=query, page=page, limit=limit)
        return [BountyResponse.from_orm(bounty) for bounty in bounties]  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to search bounties: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
