"""
Ecosystem Metrics Domain Model

Migrated from the flat domain/bounty.py to contexts/ecosystem/domain/ in v0.5.14.
This model tracks ecosystem-wide metrics for dashboards. Table name unchanged
(ecosystem_metrics) — no DB migration required.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class EcosystemMetrics(SQLModel, table=True):
    """Ecosystem-wide metrics for dashboard"""

    __tablename__ = "ecosystem_metrics"
    __table_args__ = {"extend_existing": True}

    metrics_id: str = Field(primary_key=True, default_factory=lambda: f"eco_{uuid.uuid4().hex[:8]}")

    # Time period
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    period_type: str = Field(default="hourly")  # hourly, daily, weekly

    # Developer metrics
    active_developers: int = Field(default=0)
    new_developers: int = Field(default=0)
    developer_earnings_total: float = Field(default=0.0)
    developer_earnings_average: float = Field(default=0.0)

    # Agent metrics
    total_agents: int = Field(default=0)
    active_agents: int = Field(default=0)
    agent_utilization_rate: float = Field(default=0.0)
    average_agent_performance: float = Field(default=0.0)

    # Staking metrics
    total_staked: float = Field(default=0.0)
    total_stakers: int = Field(default=0)
    average_apy: float = Field(default=0.0)
    staking_rewards_total: float = Field(default=0.0)

    # Bounty metrics
    active_bounties: int = Field(default=0)
    bounty_completion_rate: float = Field(default=0.0)
    average_bounty_reward: float = Field(default=0.0)
    bounty_volume_total: float = Field(default=0.0)

    # Treasury metrics
    treasury_balance: float = Field(default=0.0)
    treasury_inflow: float = Field(default=0.0)
    treasury_outflow: float = Field(default=0.0)
    dao_revenue: float = Field(default=0.0)

    # Token metrics
    token_circulating_supply: float = Field(default=0.0)
    token_staked_percentage: float = Field(default=0.0)
    token_burn_rate: float = Field(default=0.0)

    # Metadata
    metrics_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


__all__ = ["EcosystemMetrics"]
