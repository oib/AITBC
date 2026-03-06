"""
AMM Domain Models

Domain models for automated market making, liquidity pools, and swap transactions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel, Relationship


class PoolStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    MAINTENANCE = "maintenance"


class SwapStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LiquidityPositionStatus(str, Enum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    PENDING = "pending"


class LiquidityPool(SQLModel, table=True):
    """Liquidity pool for automated market making"""
    __tablename__ = "liquidity_pool"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    contract_pool_id: str = Field(index=True)  # Contract pool ID
    token_a: str = Field(index=True)  # Token A address
    token_b: str = Field(index=True)  # Token B address
    token_a_symbol: str = Field(index=True)  # Token A symbol
    token_b_symbol: str = Field(index=True)  # Token B symbol
    fee_percentage: float = Field(default=0.3)  # Trading fee percentage
    reserve_a: float = Field(default=0.0)  # Token A reserve
    reserve_b: float = Field(default=0.0)  # Token B reserve
    total_liquidity: float = Field(default=0.0)  # Total liquidity tokens
    total_supply: float = Field(default=0.0)  # Total LP token supply
    apr: float = Field(default=0.0)  # Annual percentage rate
    volume_24h: float = Field(default=0.0)  # 24h trading volume
    fees_24h: float = Field(default=0.0)  # 24h fee revenue
    tvl: float = Field(default=0.0)  # Total value locked
    utilization_rate: float = Field(default=0.0)  # Pool utilization rate
    price_impact_threshold: float = Field(default=0.05)  # Price impact threshold
    max_slippage: float = Field(default=0.05)  # Maximum slippage
    is_active: bool = Field(default=True, index=True)
    status: PoolStatus = Field(default=PoolStatus.ACTIVE, index=True)
    created_by: str = Field(index=True)  # Creator address
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_trade_time: Optional[datetime] = Field(default=None)
    
    # Relationships
    # DISABLED:     positions: List["LiquidityPosition"] = Relationship(back_populates="pool")
    # DISABLED:     swaps: List["SwapTransaction"] = Relationship(back_populates="pool")
    # DISABLED:     metrics: List["PoolMetrics"] = Relationship(back_populates="pool")
    # DISABLED:     incentives: List["IncentiveProgram"] = Relationship(back_populates="pool")


class LiquidityPosition(SQLModel, table=True):
    """Liquidity provider position in a pool"""
    __tablename__ = "liquidity_position"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    provider_address: str = Field(index=True)
    liquidity_amount: float = Field(default=0.0)  # Amount of liquidity tokens
    shares_owned: float = Field(default=0.0)  # Percentage of pool owned
    deposit_amount_a: float = Field(default=0.0)  # Initial token A deposit
    deposit_amount_b: float = Field(default=0.0)  # Initial token B deposit
    current_amount_a: float = Field(default=0.0)  # Current token A amount
    current_amount_b: float = Field(default=0.0)  # Current token B amount
    unrealized_pnl: float = Field(default=0.0)  # Unrealized P&L
    fees_earned: float = Field(default=0.0)  # Fees earned
    impermanent_loss: float = Field(default=0.0)  # Impermanent loss
    status: LiquidityPositionStatus = Field(default=LiquidityPositionStatus.ACTIVE, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_deposit: Optional[datetime] = Field(default=None)
    last_withdrawal: Optional[datetime] = Field(default=None)
    
    # Relationships
    # DISABLED:     pool: LiquidityPool = Relationship(back_populates="positions")
    # DISABLED:     fee_claims: List["FeeClaim"] = Relationship(back_populates="position")


class SwapTransaction(SQLModel, table=True):
    """Swap transaction executed in a pool"""
    __tablename__ = "swap_transaction"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    user_address: str = Field(index=True)
    token_in: str = Field(index=True)
    token_out: str = Field(index=True)
    amount_in: float = Field(default=0.0)
    amount_out: float = Field(default=0.0)
    price: float = Field(default=0.0)  # Execution price
    price_impact: float = Field(default=0.0)  # Price impact
    slippage: float = Field(default=0.0)  # Slippage percentage
    fee_amount: float = Field(default=0.0)  # Fee amount
    fee_percentage: float = Field(default=0.0)  # Applied fee percentage
    status: SwapStatus = Field(default=SwapStatus.PENDING, index=True)
    transaction_hash: Optional[str] = Field(default=None, index=True)
    block_number: Optional[int] = Field(default=None)
    gas_used: Optional[int] = Field(default=None)
    gas_price: Optional[float] = Field(default=None)
    executed_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    deadline: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=20))
    
    # Relationships
    # DISABLED:     pool: LiquidityPool = Relationship(back_populates="swaps")


class PoolMetrics(SQLModel, table=True):
    """Historical metrics for liquidity pools"""
    __tablename__ = "pool_metrics"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    timestamp: datetime = Field(index=True)
    total_volume_24h: float = Field(default=0.0)
    total_fees_24h: float = Field(default=0.0)
    total_value_locked: float = Field(default=0.0)
    apr: float = Field(default=0.0)
    utilization_rate: float = Field(default=0.0)
    liquidity_depth: float = Field(default=0.0)  # Liquidity depth at 1% price impact
    price_volatility: float = Field(default=0.0)  # Price volatility
    swap_count_24h: int = Field(default=0)  # Number of swaps in 24h
    unique_traders_24h: int = Field(default=0)  # Unique traders in 24h
    average_trade_size: float = Field(default=0.0)  # Average trade size
    impermanent_loss_24h: float = Field(default=0.0)  # 24h impermanent loss
    liquidity_provider_count: int = Field(default=0)  # Number of liquidity providers
    top_lps: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))  # Top LPs by share
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    # DISABLED:     pool: LiquidityPool = Relationship(back_populates="metrics")


class FeeStructure(SQLModel, table=True):
    """Fee structure for liquidity pools"""
    __tablename__ = "fee_structure"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    base_fee_percentage: float = Field(default=0.3)  # Base fee percentage
    current_fee_percentage: float = Field(default=0.3)  # Current fee percentage
    volatility_adjustment: float = Field(default=0.0)  # Volatility-based adjustment
    volume_adjustment: float = Field(default=0.0)  # Volume-based adjustment
    liquidity_adjustment: float = Field(default=0.0)  # Liquidity-based adjustment
    time_adjustment: float = Field(default=0.0)  # Time-based adjustment
    adjusted_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))
    adjustment_reason: str = Field(default="")  # Reason for adjustment
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IncentiveProgram(SQLModel, table=True):
    """Incentive program for liquidity providers"""
    __tablename__ = "incentive_program"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    program_name: str = Field(index=True)
    reward_token: str = Field(index=True)  # Reward token address
    daily_reward_amount: float = Field(default=0.0)  # Daily reward amount
    total_reward_amount: float = Field(default=0.0)  # Total reward amount
    remaining_reward_amount: float = Field(default=0.0)  # Remaining rewards
    incentive_multiplier: float = Field(default=1.0)  # Incentive multiplier
    duration_days: int = Field(default=30)  # Program duration in days
    minimum_liquidity: float = Field(default=0.0)  # Minimum liquidity to qualify
    maximum_liquidity: float = Field(default=0.0)  # Maximum liquidity cap (0 = no cap)
    vesting_period_days: int = Field(default=0)  # Vesting period (0 = no vesting)
    is_active: bool = Field(default=True, index=True)
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(days=30))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    # DISABLED:     pool: LiquidityPool = Relationship(back_populates="incentives")
    # DISABLED:     rewards: List["LiquidityReward"] = Relationship(back_populates="program")


class LiquidityReward(SQLModel, table=True):
    """Reward earned by liquidity providers"""
    __tablename__ = "liquidity_reward"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    program_id: int = Field(foreign_key="incentive_program.id", index=True)
    position_id: int = Field(foreign_key="liquidity_position.id", index=True)
    provider_address: str = Field(index=True)
    reward_amount: float = Field(default=0.0)
    reward_token: str = Field(index=True)
    liquidity_share: float = Field(default=0.0)  # Share of pool liquidity
    time_weighted_share: float = Field(default=0.0)  # Time-weighted share
    is_claimed: bool = Field(default=False, index=True)
    claimed_at: Optional[datetime] = Field(default=None)
    claim_transaction_hash: Optional[str] = Field(default=None)
    vesting_start: Optional[datetime] = Field(default=None)
    vesting_end: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    # Relationships
    # DISABLED:     program: IncentiveProgram = Relationship(back_populates="rewards")
    # DISABLED:     position: LiquidityPosition = Relationship(back_populates="fee_claims")


class FeeClaim(SQLModel, table=True):
    """Fee claim by liquidity providers"""
    __tablename__ = "fee_claim"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    position_id: int = Field(foreign_key="liquidity_position.id", index=True)
    provider_address: str = Field(index=True)
    fee_amount: float = Field(default=0.0)
    fee_token: str = Field(index=True)
    claim_period_start: datetime = Field(index=True)
    claim_period_end: datetime = Field(index=True)
    liquidity_share: float = Field(default=0.0)  # Share of pool liquidity
    is_claimed: bool = Field(default=False, index=True)
    claimed_at: Optional[datetime] = Field(default=None)
    claim_transaction_hash: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    # Relationships
    # DISABLED:     position: LiquidityPosition = Relationship(back_populates="fee_claims")


class PoolConfiguration(SQLModel, table=True):
    """Configuration settings for liquidity pools"""
    __tablename__ = "pool_configuration"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    config_key: str = Field(index=True)
    config_value: str = Field(default="")
    config_type: str = Field(default="string")  # string, number, boolean, json
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PoolAlert(SQLModel, table=True):
    """Alerts for pool events and conditions"""
    __tablename__ = "pool_alert"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    alert_type: str = Field(index=True)  # LOW_LIQUIDITY, HIGH_VOLATILITY, etc.
    severity: str = Field(index=True)  # LOW, MEDIUM, HIGH, CRITICAL
    title: str = Field(default="")
    message: str = Field(default="")
    meta_data: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    threshold_value: float = Field(default=0.0)  # Threshold that triggered alert
    current_value: float = Field(default=0.0)  # Current value
    is_acknowledged: bool = Field(default=False, index=True)
    acknowledged_by: Optional[str] = Field(default=None)
    acknowledged_at: Optional[datetime] = Field(default=None)
    is_resolved: bool = Field(default=False, index=True)
    resolved_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))


class PoolSnapshot(SQLModel, table=True):
    """Daily snapshot of pool state"""
    __tablename__ = "pool_snapshot"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    pool_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    snapshot_date: datetime = Field(index=True)
    reserve_a: float = Field(default=0.0)
    reserve_b: float = Field(default=0.0)
    total_liquidity: float = Field(default=0.0)
    price_a_to_b: float = Field(default=0.0)  # Price of A in terms of B
    price_b_to_a: float = Field(default=0.0)  # Price of B in terms of A
    volume_24h: float = Field(default=0.0)
    fees_24h: float = Field(default=0.0)
    tvl: float = Field(default=0.0)
    apr: float = Field(default=0.0)
    utilization_rate: float = Field(default=0.0)
    liquidity_provider_count: int = Field(default=0)
    swap_count_24h: int = Field(default=0)
    average_slippage: float = Field(default=0.0)
    average_price_impact: float = Field(default=0.0)
    impermanent_loss: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ArbitrageOpportunity(SQLModel, table=True):
    """Arbitrage opportunities across pools"""
    __tablename__ = "arbitrage_opportunity"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    token_a: str = Field(index=True)
    token_b: str = Field(index=True)
    pool_1_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    pool_2_id: int = Field(foreign_key="liquidity_pool.id", index=True)
    price_1: float = Field(default=0.0)  # Price in pool 1
    price_2: float = Field(default=0.0)  # Price in pool 2
    price_difference: float = Field(default=0.0)  # Price difference percentage
    potential_profit: float = Field(default=0.0)  # Potential profit amount
    gas_cost_estimate: float = Field(default=0.0)  # Estimated gas cost
    net_profit: float = Field(default=0.0)  # Net profit after gas
    required_amount: float = Field(default=0.0)  # Amount needed for arbitrage
    confidence: float = Field(default=0.0)  # Confidence in opportunity
    is_executed: bool = Field(default=False, index=True)
    executed_at: Optional[datetime] = Field(default=None)
    execution_tx_hash: Optional[str] = Field(default=None)
    actual_profit: Optional[float] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=5))
