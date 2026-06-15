"""
Staking Management API
REST API for AI agent staking system with reputation-based yield farming
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from ....domain.bounty import PerformanceTier, StakeStatus
from ....routers.users import get_current_user as _get_current_user
from ....storage import get_session
from ...blockchain.services.blockchain import BlockchainService
from ..services.staking_service import StakingService

router = APIRouter()
logger = get_logger(__name__)


def create_get_current_user_optional(session: Session = Depends(get_session)) -> Any:

    async def get_current_user_optional(request: Request | None = None) -> dict[str, Any]:
        """Optional authentication that returns default test user if no token provided"""
        try:
            if not request:
                return {"address": "test_user_address", "is_oracle": False, "is_admin": False}
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            return await _get_current_user(session, token, request)
        except Exception:
            return {"address": "test_user_address", "is_oracle": False, "is_admin": False}

    return get_current_user_optional


get_current_user_optional = create_get_current_user_optional


class StakeCreateRequest(BaseModel):
    agent_wallet: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    lock_period: int = Field(default=30, ge=1, le=365)
    auto_compound: bool = Field(default=False)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < 100.0:
            raise ValueError("Minimum stake amount is 100 AITBC")
        if v > 100000.0:
            raise ValueError("Maximum stake amount is 100,000 AITBC")
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
    unbonding_time: datetime | None
    early_unbond_penalty: float
    lock_bonus_multiplier: float
    stake_data: dict[str, Any]


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
    first_submission_time: datetime | None
    average_response_time: float | None
    total_compute_time: float | None
    energy_efficiency_score: float | None
    weekly_accuracy: list[float]
    monthly_earnings: list[float]
    agent_metadata: dict[str, Any]


class StakingPoolResponse(BaseModel):
    agent_wallet: str
    total_staked: float
    total_rewards: float
    pool_apy: float
    staker_count: int
    active_stakers: list[str]
    last_distribution_time: datetime
    distribution_frequency: int
    min_stake_amount: float
    max_stake_amount: float
    auto_compound_enabled: bool
    pool_performance_score: float
    volatility_score: float
    pool_metadata: dict[str, Any]


class StakingFilterRequest(BaseModel):
    agent_wallet: str | None = None
    status: StakeStatus | None = None
    min_amount: float | None = Field(default=None, ge=0)
    max_amount: float | None = Field(default=None, ge=0)
    agent_tier: PerformanceTier | None = None
    auto_compound: bool | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


class StakingStatsResponse(BaseModel):
    total_staked: float
    total_stakers: int
    active_stakes: int
    average_apy: float
    total_rewards_distributed: float
    top_agents: list[dict[str, Any]]
    tier_distribution: dict[str, int]
    lock_period_distribution: dict[str, int]


class AgentPerformanceUpdateRequest(BaseModel):
    agent_wallet: str = Field(..., min_length=1)
    accuracy: float = Field(..., ge=0, le=100)
    successful: bool = Field(default=True)
    response_time: float | None = Field(default=None, gt=0)
    compute_power: float | None = Field(default=None, gt=0)
    energy_efficiency: float | None = Field(default=None, ge=0, le=100)


class EarningsDistributionRequest(BaseModel):
    agent_wallet: str = Field(..., min_length=1)
    total_earnings: float = Field(..., gt=0)
    distribution_data: dict[str, Any] = Field(default_factory=dict)


def get_staking_service(session: Session = Depends(get_session)) -> StakingService:
    return StakingService(session)


def get_blockchain_service() -> BlockchainService:
    return BlockchainService()


@router.post("/stake", response_model=StakeResponse)
@rate_limit(rate=20, per=60)
async def create_stake(
    request: Request,
    stake_request: StakeCreateRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user_optional),
) -> StakeResponse:
    """Create a new stake on an agent wallet"""
    try:
        logger.info("Creating stake: %s AITBC on %s by %s", request.amount, request.agent_wallet, current_user["address"])  # type: ignore[attr-defined]
        agent_metrics = await staking_service.get_agent_metrics(request.agent_wallet)  # type: ignore[attr-defined]
        if not agent_metrics:
            raise HTTPException(status_code=404, detail="Agent not supported for staking")
        stake = await staking_service.create_stake(staker_address=current_user["address"], **request.dict())  # type: ignore[attr-defined]
        background_tasks.add_task(
            blockchain_service.create_stake_contract,
            stake.stake_id,
            request.agent_wallet,
            request.amount,
            request.lock_period,
            request.auto_compound,
        )  # type: ignore[attr-defined]
        return StakeResponse.from_orm(stake)  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create stake: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stake/{stake_id}", response_model=StakeResponse)
@rate_limit(rate=200, per=60)
async def get_stake(
    request: Request,
    stake_id: str,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user_optional),
) -> StakeResponse:
    """Get stake details"""
    try:
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        if stake.staker_address != current_user["address"]:
            raise HTTPException(status_code=403, detail="Not authorized to view this stake")
        return StakeResponse.from_orm(stake)  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get stake %s: %s", stake_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stakes", response_model=list[StakeResponse])
@rate_limit(rate=200, per=60)
async def get_stakes(
    request: Request,
    filters: StakingFilterRequest = Depends(),
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user_optional),
) -> list[StakeResponse]:
    """Get filtered list of user's stakes"""
    try:
        stakes = await staking_service.get_user_stakes(
            user_address=current_user["address"],
            agent_wallet=filters.agent_wallet,
            status=filters.status,
            min_amount=filters.min_amount,
            max_amount=filters.max_amount,
            agent_tier=filters.agent_tier,
            auto_compound=filters.auto_compound,
            page=filters.page,
            limit=filters.limit,
        )
        return [StakeResponse.from_orm(stake) for stake in stakes]  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to get stakes: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stake/{stake_id}/add", response_model=StakeResponse)
@rate_limit(rate=20, per=60)
async def add_to_stake(
    request: Request,
    stake_id: str,
    stake_request: StakeUpdateRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user_optional),
) -> StakeResponse:
    """Add more tokens to an existing stake"""
    try:
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        if stake.staker_address != current_user["address"]:
            raise HTTPException(status_code=403, detail="Not authorized to modify this stake")
        if stake.status != StakeStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Stake is not active")
        updated_stake = await staking_service.add_to_stake(stake_id=stake_id, additional_amount=request.additional_amount)  # type: ignore[attr-defined]
        background_tasks.add_task(blockchain_service.add_to_stake, stake_id, request.additional_amount)  # type: ignore[attr-defined]
        return StakeResponse.from_orm(updated_stake)  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to add to stake: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stake/{stake_id}/unbond")
@rate_limit(rate=20, per=60)
async def unbond_stake(
    request: Request,
    stake_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user_optional),
) -> dict[str, str]:
    """Initiate unbonding for a stake"""
    try:
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        if stake.staker_address != current_user["address"]:
            raise HTTPException(status_code=403, detail="Not authorized to unbond this stake")
        if stake.status != StakeStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Stake is not active")
        if datetime.now(UTC) < stake.end_time:
            raise HTTPException(status_code=400, detail="Lock period has not ended")
        await staking_service.unbond_stake(stake_id)
        background_tasks.add_task(blockchain_service.unbond_stake, stake_id)  # type: ignore[attr-defined]
        return {"message": "Unbonding initiated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to unbond stake: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stake/{stake_id}/complete")
@rate_limit(rate=20, per=60)
async def complete_unbonding(
    request: Request,
    stake_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Complete unbonding and return stake + rewards"""
    try:
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        if stake.staker_address != current_user["address"]:
            raise HTTPException(status_code=403, detail="Not authorized to complete this stake")
        if stake.status != StakeStatus.UNBONDING:
            raise HTTPException(status_code=400, detail="Stake is not unbonding")
        result = await staking_service.complete_unbonding(stake_id)
        background_tasks.add_task(blockchain_service.complete_unbonding, stake_id)  # type: ignore[attr-defined]
        return {
            "message": "Unbonding completed successfully",
            "total_amount": result["total_amount"],
            "total_rewards": result["total_rewards"],
            "penalty": result.get("penalty", 0.0),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to complete unbonding: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stake/{stake_id}/rewards")
@rate_limit(rate=200, per=60)
async def get_stake_rewards(
    request: Request,
    stake_id: str,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Get current rewards for a stake"""
    try:
        stake = await staking_service.get_stake(stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail="Stake not found")
        if stake.staker_address != current_user["address"]:
            raise HTTPException(status_code=403, detail="Not authorized to view this stake")
        rewards = await staking_service.calculate_rewards(stake_id)
        return {
            "stake_id": stake_id,
            "accumulated_rewards": stake.accumulated_rewards,
            "current_rewards": rewards,
            "total_rewards": stake.accumulated_rewards + rewards,
            "current_apy": stake.current_apy,
            "last_reward_time": stake.last_reward_time,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get stake rewards: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents/{agent_wallet}/metrics", response_model=AgentMetricsResponse)
@rate_limit(rate=200, per=60)
async def get_agent_metrics(
    request: Request,
    agent_wallet: str,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
) -> AgentMetricsResponse:
    """Get agent performance metrics"""
    try:
        metrics = await staking_service.get_agent_metrics(agent_wallet)
        if not metrics:
            raise HTTPException(status_code=404, detail="Agent not found")
        return AgentMetricsResponse.from_orm(metrics)  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get agent metrics: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents/{agent_wallet}/staking-pool", response_model=StakingPoolResponse)
@rate_limit(rate=200, per=60)
async def get_staking_pool(
    request: Request,
    agent_wallet: str,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
) -> StakingPoolResponse:
    """Get staking pool information for an agent"""
    try:
        pool = await staking_service.get_staking_pool(agent_wallet)
        if not pool:
            raise HTTPException(status_code=404, detail="Staking pool not found")
        return StakingPoolResponse.from_orm(pool)  # type: ignore[pydantic-orm]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get staking pool: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents/{agent_wallet}/apy")
@rate_limit(rate=200, per=60)
async def get_agent_apy(
    request: Request,
    agent_wallet: str,
    lock_period: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
) -> dict[str, Any]:
    """Get current APY for staking on an agent"""
    try:
        apy = await staking_service.calculate_apy(agent_wallet, lock_period)
        return {
            "agent_wallet": agent_wallet,
            "lock_period": lock_period,
            "current_apy": apy,
            "base_apy": 5.0,
            "tier_multiplier": apy / 5.0 if apy > 0 else 1.0,
        }
    except Exception as e:
        logger.error("Failed to get agent APY: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/agents/{agent_wallet}/performance")
@rate_limit(rate=20, per=60)
async def update_agent_performance(
    request: Request,
    agent_wallet: str,
    performance_request: AgentPerformanceUpdateRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user_optional),
) -> dict[str, str]:
    """Update agent performance metrics (oracle only)"""
    try:
        if not current_user.get("is_oracle", False):
            raise HTTPException(status_code=403, detail="Not authorized to update performance")
        await staking_service.update_agent_performance(agent_wallet=agent_wallet, **request.dict())  # type: ignore[attr-defined]
        background_tasks.add_task(
            blockchain_service.update_agent_performance, agent_wallet, request.accuracy, request.successful
        )  # type: ignore[attr-defined]
        return {"message": "Agent performance updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update agent performance: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/agents/{agent_wallet}/distribute-earnings")
@rate_limit(rate=20, per=60)
async def distribute_agent_earnings(
    request: Request,
    agent_wallet: str,
    earnings_request: EarningsDistributionRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Distribute agent earnings to stakers"""
    try:
        if not current_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Not authorized to distribute earnings")
        result = await staking_service.distribute_earnings(
            agent_wallet=agent_wallet, total_earnings=request.total_earnings, distribution_data=request.distribution_data
        )  # type: ignore[attr-defined]
        background_tasks.add_task(blockchain_service.distribute_earnings, agent_wallet, request.total_earnings)  # type: ignore[attr-defined]
        return {
            "message": "Earnings distributed successfully",
            "total_distributed": result["total_distributed"],
            "staker_count": result["staker_count"],
            "platform_fee": result.get("platform_fee", 0.0),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to distribute earnings: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents/supported")
@rate_limit(rate=200, per=60)
async def get_supported_agents(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    tier: PerformanceTier | None = None,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
) -> dict[str, Any]:
    """Get list of supported agents for staking"""
    try:
        agents = await staking_service.get_supported_agents(page=page, limit=limit, tier=tier)
        return {"agents": agents, "total_count": len(agents), "page": page, "limit": limit}
    except Exception as e:
        logger.error("Failed to get supported agents: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/staking/stats", response_model=StakingStatsResponse)
@rate_limit(rate=200, per=60)
async def get_staking_stats(
    request: Request,
    period: str = Query(default="daily", pattern="^(hourly|daily|weekly|monthly)$"),
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
) -> StakingStatsResponse:
    """Get staking system statistics"""
    try:
        stats = await staking_service.get_staking_stats(period=period)
        return StakingStatsResponse.from_orm(stats)  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to get staking stats: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/staking/leaderboard")
@rate_limit(rate=200, per=60)
async def get_staking_leaderboard(
    request: Request,
    period: str = Query(default="weekly", pattern="^(daily|weekly|monthly)$"),
    metric: str = Query(default="total_staked", pattern="^(total_staked|total_rewards|apy)$"),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
) -> dict[str, Any]:
    """Get staking leaderboard"""
    try:
        leaderboard = await staking_service.get_leaderboard(period=period, metric=metric, limit=limit)
        if isinstance(leaderboard, list):
            leaderboard = {
                "period": period,
                "metric": metric,
                "leaderboard": leaderboard,
                "total": len(leaderboard),
                "generated_at": datetime.now(UTC).isoformat(),
            }  # type: ignore[assignment]
        return leaderboard  # type: ignore[return-value]
    except Exception as e:
        logger.error("Failed to get staking leaderboard: %s", e)
        return {
            "period": period,
            "metric": metric,
            "leaderboard": [
                {
                    "rank": 1,
                    "agent_wallet": "ait1abc123...",
                    "total_staked": 50000.0,
                    "total_rewards": 12500.0,
                    "apy": 12.5,
                    "tier": "gold",
                },
                {
                    "rank": 2,
                    "agent_wallet": "ait1def456...",
                    "total_staked": 35000.0,
                    "total_rewards": 8750.0,
                    "apy": 11.8,
                    "tier": "silver",
                },
                {
                    "rank": 3,
                    "agent_wallet": "ait1ghi789...",
                    "total_staked": 25000.0,
                    "total_rewards": 6250.0,
                    "apy": 11.2,
                    "tier": "bronze",
                },
            ],
            "total": 3,
            "generated_at": datetime.now(UTC).isoformat(),
            "note": "Fallback data returned due to service error",
        }


@router.get("/staking/my-positions", response_model=list[StakeResponse])
@rate_limit(rate=200, per=60)
async def get_my_staking_positions(
    request: Request,
    status: StakeStatus | None = None,
    agent_wallet: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user_optional),
) -> list[StakeResponse]:
    """Get current user's staking positions"""
    try:
        stakes = await staking_service.get_user_stakes(
            user_address=current_user["address"], status=status, agent_wallet=agent_wallet, page=page, limit=limit
        )
        return [StakeResponse.from_orm(stake) for stake in stakes]  # type: ignore[pydantic-orm]
    except Exception as e:
        logger.error("Failed to get staking positions: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/staking/my-rewards")
@rate_limit(rate=200, per=60)
async def get_my_staking_rewards(
    request: Request,
    period: str = Query(default="monthly", pattern="^(daily|weekly|monthly)$"),
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    current_user: dict = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Get current user's staking rewards"""
    try:
        rewards = await staking_service.get_user_rewards(user_address=current_user["address"], period=period)
        return rewards
    except Exception as e:
        logger.error("Failed to get staking rewards: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/staking/claim-rewards")
@rate_limit(rate=20, per=60)
async def claim_staking_rewards(
    request: Request,
    stake_ids: list[str],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
    blockchain_service: BlockchainService = Depends(get_blockchain_service),
    current_user: dict = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Claim accumulated rewards for multiple stakes"""
    try:
        total_rewards = 0.0
        for stake_id in stake_ids:
            stake = await staking_service.get_stake(stake_id)
            if not stake:
                raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
            if stake.staker_address != current_user["address"]:
                raise HTTPException(status_code=403, detail=f"Not authorized to claim rewards for stake {stake_id}")
            total_rewards += stake.accumulated_rewards
        if total_rewards <= 0:
            raise HTTPException(status_code=400, detail="No rewards to claim")
        result = await staking_service.claim_rewards(stake_ids)
        background_tasks.add_task(blockchain_service.claim_rewards, stake_ids)  # type: ignore[attr-defined]
        return {
            "message": "Rewards claimed successfully",
            "total_rewards": total_rewards,
            "claimed_stakes": len(stake_ids),
            "transaction_hash": result.get("transaction_hash"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to claim rewards: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/staking/risk-assessment/{agent_wallet}")
@rate_limit(rate=200, per=60)
async def get_risk_assessment(
    request: Request,
    agent_wallet: str,
    session: Session = Depends(get_session),
    staking_service: StakingService = Depends(get_staking_service),
) -> dict[str, Any]:
    """Get risk assessment for staking on an agent"""
    try:
        assessment = await staking_service.get_risk_assessment(agent_wallet)
        return assessment
    except Exception as e:
        logger.error("Failed to get risk assessment: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
