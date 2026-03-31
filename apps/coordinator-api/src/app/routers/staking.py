from typing import Annotated

"""
Staking Management API
REST API for AI agent staking system with reputation-based yield farming
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from ..app_logging import get_logger
from ..auth import get_current_user
from ..domain.bounty import AgentMetrics, AgentStake, EcosystemMetrics, PerformanceTier, StakeStatus, StakingPool
from ..services.blockchain_service import BlockchainService
from ..services.staking_service import StakingService
from ..storage import get_session

router = APIRouter()

# Pydantic models for request/response
class StakeCreateRequest(BaseModel):
    agent_wallet: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    lock_period: int = Field(default=30, ge=1, le=365)  # days
    auto_compound: bool = Field(default=False)

    @validator('amount')
    def validate_amount(cls, v):
        if v < 100.0:
            raise ValueError('Minimum stake amount is 100 AITBC')
        if v > 100000.0:
            raise ValueError('Maximum stake amount is 100,000 AITBC')
        return v

class StakeResponse(BaseModel):
    stake_id: str
    staker_address: str
    agent_wallet: str
    amount: float
    lock_period: int
    start_time: datetime
    end_time: datetime
    status: StakeStatus
    accumulated_rewards: float
    last_reward_time: datetime
    current_apy: float
    agent_tier: PerformanceTier
    performance_multiplier: float
    auto_compound: bool
    unbonding_time: Optional[datetime]
    early_unbond_penalty: float
    lock_bonus_multiplier: float
    stake_data: Dict[str, Any]

class StakeUpdateRequest(BaseModel):
    additional_amount: float = Field(..., gt=0)

class StakeUnbondRequest(BaseModel):
    stake_id: str = Field(..., min_length=1)

class StakeCompleteRequest(BaseModel):
    stake_id: str = Field(..., min_length=1)

class AgentMetricsResponse(BaseModel):
    agent_wallet: str
    total_staked: float
    staker_count: int
    total_rewards_distributed: float
    average_accuracy: float
    total_submissions: int
    successful_submissions: int
    success_rate: float
    current_tier: PerformanceTier
    tier_score: float
    reputation_score: float
    last_update_time: datetime
    first_submission_time: Optional[datetime]
    average_response_time: Optional[float]
    total_compute_time: Optional[float]
    energy_efficiency_score: Optional[float]
    weekly_accuracy: List[float]
    monthly_earnings: List[float]
    agent_metadata: Dict[str, Any]

class StakingPoolResponse(BaseModel):
    agent_wallet: str
    total_staked: float
    total_rewards: float
    pool_apy: float
    staker_count: int
    active_stakers: List[str]
    last_distribution_time: datetime
    distribution_frequency: int
    min_stake_amount: float
    max_stake_amount: float
    auto_compound_enabled: bool
    pool_performance_score: float
    volatility_score: float
    pool_metadata: Dict[str, Any]

class StakingFilterRequest(BaseModel):
    agent_wallet: Optional[str] = None
    status: Optional[StakeStatus] = None
    min_amount: Optional[float] = Field(default=None, ge=0)
    max_amount: Optional[float] = Field(default=None, ge=0)
    agent_tier: Optional[PerformanceTier] = None
    auto_compound: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

class StakingStatsResponse(BaseModel):
    total_staked: float
    total_stakers: int
    active_stakes: int
    average_apy: float
    total_rewards_distributed: float
    top_agents: List[Dict[str, Any]]
    tier_distribution: Dict[str, int]
    lock_period_distribution: Dict[str, int]

class AgentPerformanceUpdateRequest(BaseModel):
    agent_wallet: str = Field(..., min_length=1)
    accuracy: float = Field(..., ge=0, le=100)
    successful: bool = Field(default=True)
    response_time: Optional[float] = Field(default=None, gt=0)
    compute_power: Optional[float] = Field(default=None, gt=0)
    energy_efficiency: Optional[float] = Field(default=None, ge=0, le=100)

class EarningsDistributionRequest(BaseModel):
    agent_wallet: str = Field(..., min_length=1)
    total_earnings: float = Field(..., gt=0)
    distribution_data: Dict[str, Any] = Field(default_factory=dict)

# Dependency injection
def get_staking_service(session: Annotated[Session, Depends(get_session)]) -> StakingService:
    return StakingService(session)

def get_blockchain_service() -> BlockchainService:
    return BlockchainService()

# API endpoints
@router.post("/stake", response_model=StakeResponse)
async def create_stake(
    request: StakeCreateRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Create a new stake on an agent wallet"""
    try:
        logger.info(f"Creating stake: {request.amount} AITBC on {request.agent_wallet} by {current_user['address']}")
        
        # Validate agent is supported
        agent_metrics = await staking_service.get_agent_metrics(request.agent_wallet)
        if not agent_metrics:
            raise HTTPException(status_code=404, detail="Agent not supported for staking")
        
        # Create stake in database
        stake = await staking_service.create_stake(
            staker_address=current_user['address'],
            **request.dict()
        )
        
        # Deploy stake contract in background
        background_tasks.add_task(
            blockchain_service.create_stake_contract,
            stake.stake_id,
            request.agent_wallet,
            request.amount,
            request.lock_period,
            request.auto_compound
        )
        
        return StakeResponse.from_orm(stake)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create stake: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stake/{stake_id}", response_model=StakeResponse)
async def get_stake(
    stake_id: str,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user)
):
    """Get stake details"""
    try:
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        
        # Check ownership
        if stake.staker_address != current_user['address']:
            raise HTTPException(status_code=403, detail="Not authorized to view this stake")
        
        return StakeResponse.from_orm(stake)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stake {stake_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stakes", response_model=List[StakeResponse])
async def get_stakes(
    filters: StakingFilterRequest = Depends(),
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user)
):
    """Get filtered list of user's stakes"""
    try:
        stakes = await staking_service.get_user_stakes(
            user_address=current_user['address'],
            agent_wallet=filters.agent_wallet,
            status=filters.status,
            min_amount=filters.min_amount,
            max_amount=filters.max_amount,
            agent_tier=filters.agent_tier,
            auto_compound=filters.auto_compound,
            page=filters.page,
            limit=filters.limit
        )
        
        return [StakeResponse.from_orm(stake) for stake in stakes]
        
    except Exception as e:
        logger.error(f"Failed to get stakes: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stake/{stake_id}/add", response_model=StakeResponse)
async def add_to_stake(
    stake_id: str,
    request: StakeUpdateRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Add more tokens to an existing stake"""
    try:
        # Get stake and verify ownership
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        
        if stake.staker_address != current_user['address']:
            raise HTTPException(status_code=403, detail="Not authorized to modify this stake")
        
        if stake.status != StakeStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Stake is not active")
        
        # Update stake
        updated_stake = await staking_service.add_to_stake(
            stake_id=stake_id,
            additional_amount=request.additional_amount
        )
        
        # Update blockchain in background
        background_tasks.add_task(
            blockchain_service.add_to_stake,
            stake_id,
            request.additional_amount
        )
        
        return StakeResponse.from_orm(updated_stake)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add to stake: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stake/{stake_id}/unbond")
async def unbond_stake(
    stake_id: str,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Initiate unbonding for a stake"""
    try:
        # Get stake and verify ownership
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        
        if stake.staker_address != current_user['address']:
            raise HTTPException(status_code=403, detail="Not authorized to unbond this stake")
        
        if stake.status != StakeStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Stake is not active")
        
        if datetime.utcnow() < stake.end_time:
            raise HTTPException(status_code=400, detail="Lock period has not ended")
        
        # Initiate unbonding
        await staking_service.unbond_stake(stake_id)
        
        # Update blockchain in background
        background_tasks.add_task(
            blockchain_service.unbond_stake,
            stake_id
        )
        
        return {"message": "Unbonding initiated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unbond stake: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stake/{stake_id}/complete")
async def complete_unbonding(
    stake_id: str,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Complete unbonding and return stake + rewards"""
    try:
        # Get stake and verify ownership
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        
        if stake.staker_address != current_user['address']:
            raise HTTPException(status_code=403, detail="Not authorized to complete this stake")
        
        if stake.status != StakeStatus.UNBONDING:
            raise HTTPException(status_code=400, detail="Stake is not unbonding")
        
        # Complete unbonding
        result = await staking_service.complete_unbonding(stake_id)
        
        # Update blockchain in background
        background_tasks.add_task(
            blockchain_service.complete_unbonding,
            stake_id
        )
        
        return {
            "message": "Unbonding completed successfully",
            "total_amount": result["total_amount"],
            "total_rewards": result["total_rewards"],
            "penalty": result.get("penalty", 0.0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete unbonding: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stake/{stake_id}/rewards")
async def get_stake_rewards(
    stake_id: str,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user)
):
    """Get current rewards for a stake"""
    try:
        # Get stake and verify ownership
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        
        if stake.staker_address != current_user['address']:
            raise HTTPException(status_code=403, detail="Not authorized to view this stake")
        
        # Calculate rewards
        rewards = await staking_service.calculate_rewards(stake_id)
        
        return {
            "stake_id": stake_id,
            "accumulated_rewards": stake.accumulated_rewards,
            "current_rewards": rewards,
            "total_rewards": stake.accumulated_rewards + rewards,
            "current_apy": stake.current_apy,
            "last_reward_time": stake.last_reward_time
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stake rewards: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/agents/{agent_wallet}/metrics", response_model=AgentMetricsResponse)
async def get_agent_metrics(
    agent_wallet: str,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service)
):
    """Get agent performance metrics"""
    try:
        metrics = await staking_service.get_agent_metrics(agent_wallet)
        if not metrics:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        return AgentMetricsResponse.from_orm(metrics)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent metrics: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/agents/{agent_wallet}/staking-pool", response_model=StakingPoolResponse)
async def get_staking_pool(
    agent_wallet: str,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service)
):
    """Get staking pool information for an agent"""
    try:
        pool = await staking_service.get_staking_pool(agent_wallet)
        if not pool:
            raise HTTPException(status_code=404, detail="Staking pool not found")
        
        return StakingPoolResponse.from_orm(pool)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get staking pool: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/agents/{agent_wallet}/apy")
async def get_agent_apy(
    agent_wallet: str,
    lock_period: int = Field(default=30, ge=1, le=365),
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service)
):
    """Get current APY for staking on an agent"""
    try:
        apy = await staking_service.calculate_apy(agent_wallet, lock_period)
        
        return {
            "agent_wallet": agent_wallet,
            "lock_period": lock_period,
            "current_apy": apy,
            "base_apy": 5.0,  # Base APY
            "tier_multiplier": apy / 5.0 if apy > 0 else 1.0
        }
        
    except Exception as e:
        logger.error(f"Failed to get agent APY: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/agents/{agent_wallet}/performance")
async def update_agent_performance(
    agent_wallet: str,
    request: AgentPerformanceUpdateRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Update agent performance metrics (oracle only)"""
    try:
        # Check permissions
        if not current_user.get('is_oracle', False):
            raise HTTPException(status_code=403, detail="Not authorized to update performance")
        
        # Update performance
        await staking_service.update_agent_performance(
            agent_wallet=agent_wallet,
            **request.dict()
        )
        
        # Update blockchain in background
        background_tasks.add_task(
            blockchain_service.update_agent_performance,
            agent_wallet,
            request.accuracy,
            request.successful
        )
        
        return {"message": "Agent performance updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent performance: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/agents/{agent_wallet}/distribute-earnings")
async def distribute_agent_earnings(
    agent_wallet: str,
    request: EarningsDistributionRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Distribute agent earnings to stakers"""
    try:
        # Check permissions
        if not current_user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Not authorized to distribute earnings")
        
        # Distribute earnings
        result = await staking_service.distribute_earnings(
            agent_wallet=agent_wallet,
            total_earnings=request.total_earnings,
            distribution_data=request.distribution_data
        )
        
        # Update blockchain in background
        background_tasks.add_task(
            blockchain_service.distribute_earnings,
            agent_wallet,
            request.total_earnings
        )
        
        return {
            "message": "Earnings distributed successfully",
            "total_distributed": result["total_distributed"],
            "staker_count": result["staker_count"],
            "platform_fee": result.get("platform_fee", 0.0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to distribute earnings: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/agents/supported")
async def get_supported_agents(
    page: int = Field(default=1, ge=1),
    limit: int = Field(default=50, ge=1, le=100),
    tier: Optional[PerformanceTier] = None,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service)
):
    """Get list of supported agents for staking"""
    try:
        agents = await staking_service.get_supported_agents(
            page=page,
            limit=limit,
            tier=tier
        )
        
        return {
            "agents": agents,
            "total_count": len(agents),
            "page": page,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Failed to get supported agents: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/staking/stats", response_model=StakingStatsResponse)
async def get_staking_stats(
    period: str = Field(default="daily", regex="^(hourly|daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service)
):
    """Get staking system statistics"""
    try:
        stats = await staking_service.get_staking_stats(period=period)
        
        return StakingStatsResponse.from_orm(stats)
        
    except Exception as e:
        logger.error(f"Failed to get staking stats: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/staking/leaderboard")
async def get_staking_leaderboard(
    period: str = Field(default="weekly", regex="^(daily|weekly|monthly)$"),
    metric: str = Field(default="total_staked", regex="^(total_staked|total_rewards|apy)$"),
    limit: int = Field(default=50, ge=1, le=100),
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service)
):
    """Get staking leaderboard"""
    try:
        leaderboard = await staking_service.get_leaderboard(
            period=period,
            metric=metric,
            limit=limit
        )
        
        return leaderboard
        
    except Exception as e:
        logger.error(f"Failed to get staking leaderboard: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/staking/my-positions", response_model=List[StakeResponse])
async def get_my_staking_positions(
    status: Optional[StakeStatus] = None,
    agent_wallet: Optional[str] = None,
    page: int = Field(default=1, ge=1),
    limit: int = Field(default=20, ge=1, le=100),
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user)
):
    """Get current user's staking positions"""
    try:
        stakes = await staking_service.get_user_stakes(
            user_address=current_user['address'],
            status=status,
            agent_wallet=agent_wallet,
            page=page,
            limit=limit
        )
        
        return [StakeResponse.from_orm(stake) for stake in stakes]
        
    except Exception as e:
        logger.error(f"Failed to get staking positions: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/staking/my-rewards")
async def get_my_staking_rewards(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user)
):
    """Get current user's staking rewards"""
    try:
        rewards = await staking_service.get_user_rewards(
            user_address=current_user['address'],
            period=period
        )
        
        return rewards
        
    except Exception as e:
        logger.error(f"Failed to get staking rewards: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/staking/claim-rewards")
async def claim_staking_rewards(
    stake_ids: List[str],
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user)
):
    """Claim accumulated rewards for multiple stakes"""
    try:
        # Verify ownership of all stakes
        total_rewards = 0.0
        for stake_id in stake_ids:
            stake = await staking_service.get_stake(stake_id)
            if not stake:
                raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
            
            if stake.staker_address != current_user['address']:
                raise HTTPException(status_code=403, detail=f"Not authorized to claim rewards for stake {stake_id}")
            
            total_rewards += stake.accumulated_rewards
        
        if total_rewards <= 0:
            raise HTTPException(status_code=400, detail="No rewards to claim")
        
        # Claim rewards
        result = await staking_service.claim_rewards(stake_ids)
        
        # Update blockchain in background
        background_tasks.add_task(
            blockchain_service.claim_rewards,
            stake_ids
        )
        
        return {
            "message": "Rewards claimed successfully",
            "total_rewards": total_rewards,
            "claimed_stakes": len(stake_ids),
            "transaction_hash": result.get("transaction_hash")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to claim rewards: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/staking/risk-assessment/{agent_wallet}")
async def get_risk_assessment(
    agent_wallet: str,
    session: Annotated[Session, Depends(get_session)],
    staking_service: StakingService = Depends(get_staking_service)
):
    """Get risk assessment for staking on an agent"""
    try:
        assessment = await staking_service.get_risk_assessment(agent_wallet)
        
        return assessment
        
    except Exception as e:
        logger.error(f"Failed to get risk assessment: {e}")
        raise HTTPException(status_code=400, detail=str(e))
