"""
Agent Portfolio Domain Models

Domain models for agent portfolio management, trading strategies, and risk assessment.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel, Relationship


class StrategyType(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    DYNAMIC = "dynamic"


class TradeStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PortfolioStrategy(SQLModel, table=True):
    """Trading strategy configuration for agent portfolios"""
    __tablename__ = "portfolio_strategy"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    strategy_type: StrategyType = Field(index=True)
    target_allocations: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    max_drawdown: float = Field(default=20.0)  # Maximum drawdown percentage
    rebalance_frequency: int = Field(default=86400)  # Rebalancing frequency in seconds
    volatility_threshold: float = Field(default=15.0)  # Volatility threshold for rebalancing
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    # DISABLED:     portfolios: List["AgentPortfolio"] = Relationship(back_populates="strategy")


class AgentPortfolio(SQLModel, table=True):
    """Portfolio managed by an autonomous agent"""
    __tablename__ = "agent_portfolio"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_address: str = Field(index=True)
    strategy_id: int = Field(foreign_key="portfolio_strategy.id", index=True)
    contract_portfolio_id: Optional[str] = Field(default=None, index=True)
    initial_capital: float = Field(default=0.0)
    total_value: float = Field(default=0.0)
    risk_score: float = Field(default=0.0)  # Risk score (0-100)
    risk_tolerance: float = Field(default=50.0)  # Risk tolerance percentage
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_rebalance: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    # DISABLED:     strategy: PortfolioStrategy = Relationship(back_populates="portfolios")
    # DISABLED:     assets: List["PortfolioAsset"] = Relationship(back_populates="portfolio")
    # DISABLED:     trades: List["PortfolioTrade"] = Relationship(back_populates="portfolio")
    # DISABLED:     risk_metrics: Optional["RiskMetrics"] = Relationship(back_populates="portfolio")


class PortfolioAsset(SQLModel, table=True):
    """Asset holdings within a portfolio"""
    __tablename__ = "portfolio_asset"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    token_symbol: str = Field(index=True)
    token_address: str = Field(index=True)
    balance: float = Field(default=0.0)
    target_allocation: float = Field(default=0.0)  # Target allocation percentage
    current_allocation: float = Field(default=0.0)  # Current allocation percentage
    average_cost: float = Field(default=0.0)  # Average cost basis
    unrealized_pnl: float = Field(default=0.0)  # Unrealized profit/loss
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    # DISABLED:     portfolio: AgentPortfolio = Relationship(back_populates="assets")


class PortfolioTrade(SQLModel, table=True):
    """Trade executed within a portfolio"""
    __tablename__ = "portfolio_trade"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    sell_token: str = Field(index=True)
    buy_token: str = Field(index=True)
    sell_amount: float = Field(default=0.0)
    buy_amount: float = Field(default=0.0)
    price: float = Field(default=0.0)
    fee_amount: float = Field(default=0.0)
    status: TradeStatus = Field(default=TradeStatus.PENDING, index=True)
    transaction_hash: Optional[str] = Field(default=None, index=True)
    executed_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    # Relationships
    # DISABLED:     portfolio: AgentPortfolio = Relationship(back_populates="trades")


class RiskMetrics(SQLModel, table=True):
    """Risk assessment metrics for a portfolio"""
    __tablename__ = "risk_metrics"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    volatility: float = Field(default=0.0)  # Portfolio volatility
    max_drawdown: float = Field(default=0.0)  # Maximum drawdown
    sharpe_ratio: float = Field(default=0.0)  # Sharpe ratio
    beta: float = Field(default=0.0)  # Beta coefficient
    alpha: float = Field(default=0.0)  # Alpha coefficient
    var_95: float = Field(default=0.0)  # Value at Risk at 95% confidence
    var_99: float = Field(default=0.0)  # Value at Risk at 99% confidence
    correlation_matrix: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, index=True)
    overall_risk_score: float = Field(default=0.0)  # Overall risk score (0-100)
    stress_test_results: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    # DISABLED:     portfolio: AgentPortfolio = Relationship(back_populates="risk_metrics")


class RebalanceHistory(SQLModel, table=True):
    """History of portfolio rebalancing events"""
    __tablename__ = "rebalance_history"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    trigger_reason: str = Field(index=True)  # Reason for rebalancing
    pre_rebalance_value: float = Field(default=0.0)
    post_rebalance_value: float = Field(default=0.0)
    trades_executed: int = Field(default=0)
    rebalance_cost: float = Field(default=0.0)  # Cost of rebalancing
    execution_time_ms: int = Field(default=0)  # Execution time in milliseconds
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class PerformanceMetrics(SQLModel, table=True):
    """Performance metrics for portfolios"""
    __tablename__ = "performance_metrics"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    period: str = Field(index=True)  # Performance period (1d, 7d, 30d, etc.)
    total_return: float = Field(default=0.0)  # Total return percentage
    annualized_return: float = Field(default=0.0)  # Annualized return
    volatility: float = Field(default=0.0)  # Period volatility
    max_drawdown: float = Field(default=0.0)  # Maximum drawdown in period
    win_rate: float = Field(default=0.0)  # Win rate percentage
    profit_factor: float = Field(default=0.0)  # Profit factor
    sharpe_ratio: float = Field(default=0.0)  # Sharpe ratio
    sortino_ratio: float = Field(default=0.0)  # Sortino ratio
    calmar_ratio: float = Field(default=0.0)  # Calmar ratio
    benchmark_return: float = Field(default=0.0)  # Benchmark return
    alpha: float = Field(default=0.0)  # Alpha vs benchmark
    beta: float = Field(default=0.0)  # Beta vs benchmark
    tracking_error: float = Field(default=0.0)  # Tracking error
    information_ratio: float = Field(default=0.0)  # Information ratio
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime = Field(default_factory=datetime.utcnow)
    period_end: datetime = Field(default_factory=datetime.utcnow)


class PortfolioAlert(SQLModel, table=True):
    """Alerts for portfolio events"""
    __tablename__ = "portfolio_alert"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    alert_type: str = Field(index=True)  # Type of alert
    severity: str = Field(index=True)  # Severity level
    message: str = Field(default="")
    meta_data: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    is_acknowledged: bool = Field(default=False, index=True)
    acknowledged_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    resolved_at: Optional[datetime] = Field(default=None)


class StrategySignal(SQLModel, table=True):
    """Trading signals generated by strategies"""
    __tablename__ = "strategy_signal"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_id: int = Field(foreign_key="portfolio_strategy.id", index=True)
    signal_type: str = Field(index=True)  # BUY, SELL, HOLD
    token_symbol: str = Field(index=True)
    confidence: float = Field(default=0.0)  # Confidence level (0-1)
    price_target: float = Field(default=0.0)  # Target price
    stop_loss: float = Field(default=0.0)  # Stop loss price
    time_horizon: str = Field(default="1d")  # Time horizon
    reasoning: str = Field(default="")  # Signal reasoning
    meta_data: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    is_executed: bool = Field(default=False, index=True)
    executed_at: Optional[datetime] = Field(default=None)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class PortfolioSnapshot(SQLModel, table=True):
    """Daily snapshot of portfolio state"""
    __tablename__ = "portfolio_snapshot"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    snapshot_date: datetime = Field(index=True)
    total_value: float = Field(default=0.0)
    cash_balance: float = Field(default=0.0)
    asset_count: int = Field(default=0)
    top_holdings: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    sector_allocation: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    geographic_allocation: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    risk_metrics: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    performance_metrics: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TradingRule(SQLModel, table=True):
    """Trading rules and constraints for portfolios"""
    __tablename__ = "trading_rule"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    portfolio_id: int = Field(foreign_key="agent_portfolio.id", index=True)
    rule_type: str = Field(index=True)  # Type of rule
    rule_name: str = Field(index=True)
    parameters: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    is_active: bool = Field(default=True, index=True)
    priority: int = Field(default=0)  # Rule priority (higher = more important)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MarketCondition(SQLModel, table=True):
    """Market conditions affecting portfolio decisions"""
    __tablename__ = "market_condition"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    condition_type: str = Field(index=True)  # BULL, BEAR, SIDEWAYS, VOLATILE
    market_index: str = Field(index=True)  # Market index (SPY, QQQ, etc.)
    confidence: float = Field(default=0.0)  # Confidence in condition
    indicators: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    sentiment_score: float = Field(default=0.0)  # Market sentiment score
    volatility_index: float = Field(default=0.0)  # VIX or similar
    trend_strength: float = Field(default=0.0)  # Trend strength
    support_level: float = Field(default=0.0)  # Support level
    resistance_level: float = Field(default=0.0)  # Resistance level
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))
