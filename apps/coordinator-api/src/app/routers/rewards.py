from typing import Annotated

from sqlalchemy.orm import Session

"""
Reward System API Endpoints
REST API for agent rewards, incentives, and performance-based earnings
"""

from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from aitbc import get_logger

logger = get_logger(__name__)

from ..domain.rewards import AgentRewardProfile, RewardStatus, RewardTier, RewardType
from ..services.reward_service import RewardEngine
from ..storage import get_session

router = APIRouter(prefix="/v1/rewards", tags=["rewards"])


# Pydantic models for API requests/responses
class RewardProfileResponse(BaseModel):
    """Response model for reward profile"""
    agent_id: str
    current_tier: str
    tier_progress: float
    base_earnings: float
    bonus_earnings: float
    total_earnings: float
    lifetime_earnings: float
    rewards_distributed: int
    current_streak: int
    longest_streak: int
    performance_score: float
    loyalty_score: float
    referral_count: int
    community_contributions: int
    last_reward_date: Optional[str]
    recent_calculations: List[Dict[str, Any]]
    recent_distributions: List[Dict[str, Any]]


class RewardRequest(BaseModel):
    """Request model for reward calculation and distribution"""
    agent_id: str
    reward_type: RewardType
    base_amount: float = Field(..., gt=0, description="Base reward amount in AITBC")
    performance_metrics: Dict[str, Any] = Field(..., description="Performance metrics for bonus calculation")
    reference_date: Optional[str] = Field(default=None, description="Reference date for calculation")


class RewardResponse(BaseModel):
    """Response model for reward distribution"""
    calculation_id: str
    distribution_id: str
    reward_amount: float
    reward_type: str
    tier_multiplier: float
    total_bonus: float
    status: str


class RewardAnalyticsResponse(BaseModel):
    """Response model for reward analytics"""
    period_type: str
    start_date: str
    end_date: str
    total_rewards_distributed: float
    total_agents_rewarded: int
    average_reward_per_agent: float
    tier_distribution: Dict[str, int]
    total_distributions: int


class TierProgressResponse(BaseModel):
    """Response model for tier progress"""
    agent_id: str
    current_tier: str
    next_tier: Optional[str]
    tier_progress: float
    trust_score: float
    requirements_met: Dict[str, bool]
    benefits: Dict[str, Any]


class BatchProcessResponse(BaseModel):
    """Response model for batch processing"""
    processed: int
    failed: int
    total: int


class MilestoneResponse(BaseModel):
    """Response model for milestone achievements"""
    id: str
    agent_id: str
    milestone_type: str
    milestone_name: str
    target_value: float
    current_value: float
    progress_percentage: float
    reward_amount: float
    is_completed: bool
    is_claimed: bool
    completed_at: Optional[str]
    claimed_at: Optional[str]


# API Endpoints

@router.get("/profile/{agent_id}", response_model=RewardProfileResponse)
async def get_reward_profile(
    agent_id: str,
    session: Session = Depends(get_session)
) -> RewardProfileResponse:
    """Get comprehensive reward profile for an agent"""
    
    reward_engine = RewardEngine(session)
    
    try:
        profile_data = await reward_engine.get_reward_summary(agent_id)
        
        if "error" in profile_data:
            raise HTTPException(status_code=404, detail=profile_data["error"])
        
        return RewardProfileResponse(**profile_data)
        
    except Exception as e:
        logger.error(f"Error getting reward profile for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/profile/{agent_id}")
async def create_reward_profile(
    agent_id: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Create a new reward profile for an agent"""
    
    reward_engine = RewardEngine(session)
    
    try:
        profile = await reward_engine.create_reward_profile(agent_id)
        
        return {
            "message": "Reward profile created successfully",
            "agent_id": profile.agent_id,
            "current_tier": profile.current_tier.value,
            "tier_progress": profile.tier_progress,
            "created_at": profile.created_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating reward profile for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/calculate-and-distribute", response_model=RewardResponse)
async def calculate_and_distribute_reward(
    reward_request: RewardRequest,
    session: Session = Depends(get_session)
) -> RewardResponse:
    """Calculate and distribute reward for an agent"""
    
    reward_engine = RewardEngine(session)
    
    try:
        # Parse reference date if provided
        reference_date = None
        if reward_request.reference_date:
            reference_date = datetime.fromisoformat(reward_request.reference_date)
        
        # Calculate and distribute reward
        result = await reward_engine.calculate_and_distribute_reward(
            agent_id=reward_request.agent_id,
            reward_type=reward_request.reward_type,
            base_amount=reward_request.base_amount,
            performance_metrics=reward_request.performance_metrics,
            reference_date=reference_date
        )
        
        return RewardResponse(
            calculation_id=result["calculation_id"],
            distribution_id=result["distribution_id"],
            reward_amount=result["reward_amount"],
            reward_type=result["reward_type"],
            tier_multiplier=result["tier_multiplier"],
            total_bonus=result["total_bonus"],
            status=result["status"]
        )
        
    except Exception as e:
        logger.error(f"Error calculating and distributing reward: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tier-progress/{agent_id}", response_model=TierProgressResponse)
async def get_tier_progress(
    agent_id: str,
    session: Session = Depends(get_session)
) -> TierProgressResponse:
    """Get tier progress information for an agent"""
    
    reward_engine = RewardEngine(session)
    
    try:
        # Get reward profile
        profile = session.execute(
            select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)
        ).first()
        
        if not profile:
            raise HTTPException(status_code=404, detail="Reward profile not found")
        
        # Get reputation for trust score
        from ..domain.reputation import AgentReputation
        reputation = session.execute(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        trust_score = reputation.trust_score if reputation else 500.0
        
        # Determine next tier
        current_tier = profile.current_tier
        next_tier = None
        if current_tier == RewardTier.BRONZE:
            next_tier = RewardTier.SILVER
        elif current_tier == RewardTier.SILVER:
            next_tier = RewardTier.GOLD
        elif current_tier == RewardTier.GOLD:
            next_tier = RewardTier.PLATINUM
        elif current_tier == RewardTier.PLATINUM:
            next_tier = RewardTier.DIAMOND
        
        # Calculate requirements met
        requirements_met = {
            "minimum_trust_score": trust_score >= 400,
            "minimum_performance": profile.performance_score >= 3.0,
            "minimum_activity": profile.rewards_distributed >= 1,
            "minimum_earnings": profile.total_earnings >= 0.1
        }
        
        # Get tier benefits
        tier_benefits = {
            "max_concurrent_jobs": 1,
            "priority_boost": 1.0,
            "fee_discount": 0.0,
            "support_level": "basic"
        }
        
        if current_tier == RewardTier.SILVER:
            tier_benefits.update({
                "max_concurrent_jobs": 2,
                "priority_boost": 1.1,
                "fee_discount": 5.0,
                "support_level": "priority"
            })
        elif current_tier == RewardTier.GOLD:
            tier_benefits.update({
                "max_concurrent_jobs": 3,
                "priority_boost": 1.2,
                "fee_discount": 10.0,
                "support_level": "priority"
            })
        elif current_tier == RewardTier.PLATINUM:
            tier_benefits.update({
                "max_concurrent_jobs": 5,
                "priority_boost": 1.5,
                "fee_discount": 15.0,
                "support_level": "premium"
            })
        elif current_tier == RewardTier.DIAMOND:
            tier_benefits.update({
                "max_concurrent_jobs": 10,
                "priority_boost": 2.0,
                "fee_discount": 20.0,
                "support_level": "premium"
            })
        
        return TierProgressResponse(
            agent_id=agent_id,
            current_tier=current_tier.value,
            next_tier=next_tier.value if next_tier else None,
            tier_progress=profile.tier_progress,
            trust_score=trust_score,
            requirements_met=requirements_met,
            benefits=tier_benefits
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tier progress for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/batch-process", response_model=BatchProcessResponse)
async def batch_process_pending_rewards(
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of rewards to process"),
    session: Session = Depends(get_session),
) -> BatchProcessResponse:
    """Process pending reward distributions in batch"""
    
    reward_engine = RewardEngine(session)
    
    try:
        result = await reward_engine.batch_process_pending_rewards(limit)
        
        return BatchProcessResponse(
            processed=result["processed"],
            failed=result["failed"],
            total=result["total"]
        )
        
    except Exception as e:
        logger.error(f"Error batch processing rewards: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics", response_model=RewardAnalyticsResponse)
async def get_reward_analytics(
    period_type: str = Query(default="daily", description="Period type: daily, weekly, monthly"),
    start_date: Optional[str] = Query(default=None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(default=None, description="End date (ISO format)"),
    session: Session = Depends(get_session)
) -> RewardAnalyticsResponse:
    """Get reward system analytics"""
    
    reward_engine = RewardEngine(session)
    
    try:
        # Parse dates if provided
        start_dt = None
        end_dt = None
        if start_date:
            start_dt = datetime.fromisoformat(start_date)
        if end_date:
            end_dt = datetime.fromisoformat(end_date)
        
        analytics_data = await reward_engine.get_reward_analytics(
            period_type=period_type,
            start_date=start_dt,
            end_date=end_dt
        )
        
        return RewardAnalyticsResponse(**analytics_data)
        
    except Exception as e:
        logger.error(f"Error getting reward analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leaderboard")
async def get_reward_leaderboard(
    tier: Optional[str] = Query(default=None, description="Filter by tier"),
    period: str = Query(default="weekly", description="Period: daily, weekly, monthly"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get reward leaderboard"""
    
    try:
        # Calculate date range based on period
        if period == "daily":
            start_date = datetime.now(datetime.UTC) - timedelta(days=1)
        elif period == "weekly":
            start_date = datetime.now(datetime.UTC) - timedelta(days=7)
        elif period == "monthly":
            start_date = datetime.now(datetime.UTC) - timedelta(days=30)
        else:
            start_date = datetime.now(datetime.UTC) - timedelta(days=7)
        
        # Query reward profiles
        query = select(AgentRewardProfile).where(
            AgentRewardProfile.last_activity >= start_date
        )
        
        if tier:
            query = query.where(AgentRewardProfile.current_tier == tier)
        
        profiles = session.execute(
            query.order_by(AgentRewardProfile.total_earnings.desc()).limit(limit)
        ).all()
        
        leaderboard = []
        for rank, profile in enumerate(profiles, 1):
            leaderboard.append({
                "rank": rank,
                "agent_id": profile.agent_id,
                "current_tier": profile.current_tier.value,
                "total_earnings": profile.total_earnings,
                "lifetime_earnings": profile.lifetime_earnings,
                "rewards_distributed": profile.rewards_distributed,
                "current_streak": profile.current_streak,
                "performance_score": profile.performance_score
            })
        
        return leaderboard
        
    except Exception as e:
        logger.error(f"Error getting reward leaderboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tiers")
async def get_reward_tiers(
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get reward tier configurations"""
    
    try:
        from ..domain.rewards import RewardTierConfig
        
        tier_configs = session.execute(
            select(RewardTierConfig).where(RewardTierConfig.is_active == True)
        ).all()
        
        tiers = []
        for config in tier_configs:
            tiers.append({
                "tier": config.tier.value,
                "min_trust_score": config.min_trust_score,
                "base_multiplier": config.base_multiplier,
                "performance_bonus_multiplier": config.performance_bonus_multiplier,
                "max_concurrent_jobs": config.max_concurrent_jobs,
                "priority_boost": config.priority_boost,
                "fee_discount": config.fee_discount,
                "support_level": config.support_level,
                "tier_requirements": config.tier_requirements,
                "tier_benefits": config.tier_benefits
            })
        
        return sorted(tiers, key=lambda x: x["min_trust_score"])
        
    except Exception as e:
        logger.error(f"Error getting reward tiers: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/milestones/{agent_id}")
async def get_agent_milestones(
    agent_id: str,
    include_completed: bool = Query(default=True, description="Include completed milestones"),
    session: Session = Depends(get_session)
) -> List[MilestoneResponse]:
    """Get milestones for an agent"""
    
    try:
        from ..domain.rewards import RewardMilestone
        
        query = select(RewardMilestone).where(RewardMilestone.agent_id == agent_id)
        
        if not include_completed:
            query = query.where(RewardMilestone.is_completed == False)
        
        milestones = session.execute(
            query.order_by(RewardMilestone.created_at.desc())
        ).all()
        
        return [
            MilestoneResponse(
                id=milestone.id,
                agent_id=milestone.agent_id,
                milestone_type=milestone.milestone_type,
                milestone_name=milestone.milestone_name,
                target_value=milestone.target_value,
                current_value=milestone.current_value,
                progress_percentage=milestone.progress_percentage,
                reward_amount=milestone.reward_amount,
                is_completed=milestone.is_completed,
                is_claimed=milestone.is_claimed,
                completed_at=milestone.completed_at.isoformat() if milestone.completed_at else None,
                claimed_at=milestone.claimed_at.isoformat() if milestone.claimed_at else None
            )
            for milestone in milestones
        ]
        
    except Exception as e:
        logger.error(f"Error getting milestones for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/distributions/{agent_id}")
async def get_reward_distributions(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get reward distribution history for an agent"""
    
    try:
        from ..domain.rewards import RewardDistribution
        
        query = select(RewardDistribution).where(RewardDistribution.agent_id == agent_id)
        
        if status:
            query = query.where(RewardDistribution.status == status)
        
        distributions = session.execute(
            query.order_by(RewardDistribution.created_at.desc()).limit(limit)
        ).all()
        
        return [
            {
                "id": distribution.id,
                "reward_amount": distribution.reward_amount,
                "reward_type": distribution.reward_type.value,
                "status": distribution.status.value,
                "distribution_method": distribution.distribution_method,
                "transaction_id": distribution.transaction_id,
                "transaction_status": distribution.transaction_status,
                "created_at": distribution.created_at.isoformat(),
                "processed_at": distribution.processed_at.isoformat() if distribution.processed_at else None,
                "error_message": distribution.error_message
            }
            for distribution in distributions
        ]
        
    except Exception as e:
        logger.error(f"Error getting distributions for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/simulate-reward")
async def simulate_reward_calculation(
    reward_request: RewardRequest,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Simulate reward calculation without distributing"""
    
    reward_engine = RewardEngine(session)
    
    try:
        # Ensure reward profile exists
        await reward_engine.create_reward_profile(reward_request.agent_id)
        
        # Calculate reward only (no distribution)
        reward_calculation = reward_engine.calculator.calculate_total_reward(
            reward_request.agent_id, 
            reward_request.base_amount, 
            reward_request.performance_metrics, 
            session
        )
        
        return {
            "agent_id": reward_request.agent_id,
            "reward_type": reward_request.reward_type.value,
            "base_amount": reward_request.base_amount,
            "tier_multiplier": reward_calculation["tier_multiplier"],
            "performance_bonus": reward_calculation["performance_bonus"],
            "loyalty_bonus": reward_calculation["loyalty_bonus"],
            "referral_bonus": reward_calculation["referral_bonus"],
            "milestone_bonus": reward_calculation["milestone_bonus"],
            "effective_multiplier": reward_calculation["effective_multiplier"],
            "total_reward": reward_calculation["total_reward"],
            "trust_score": reward_calculation["trust_score"],
            "simulation": True
        }
        
    except Exception as e:
        logger.error(f"Error simulating reward calculation: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
