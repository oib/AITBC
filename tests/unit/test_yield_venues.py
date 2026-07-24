"""Unit tests for aitbc.agent_economics yield venues (v0.13.0 §A4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    AbstractYieldAdapter,
    YieldHarvest,
    YieldOpportunity,
    YieldRegistry,
    YieldStrategy,
    YieldVenue,
    YieldVenuePosition,
)
from aitbc.risk import RiskLevel


def test_yield_opportunity_validation() -> None:
    opportunity = YieldOpportunity(
        venue=YieldVenue.STAKING,
        chain_id="ait-hub",
        token="AITBC",
        apy=Decimal("12.5"),
        tvl=Decimal("1000000"),
    )
    assert opportunity.risk_level == RiskLevel.MEDIUM


def test_yield_strategy_allows_venue() -> None:
    strategy = YieldStrategy(
        strategy_id="s1",
        agent_id="agent-a",
        venues=[YieldVenue.STAKING, YieldVenue.LENDING],
    )
    assert strategy.allows_venue(YieldVenue.STAKING) is True
    assert strategy.allows_venue(YieldVenue.LIQUIDITY_POOL) is False


def test_yield_venue_position_harvest() -> None:
    position = YieldVenuePosition(
        position_id="p1",
        agent_id="agent-a",
        venue=YieldVenue.STAKING,
        chain_id="ait-hub",
        token="AITBC",
        principal=Decimal("100"),
        rewards=Decimal("10"),
    )
    harvested = position.harvest()
    assert harvested == Decimal("10")
    assert position.rewards == Decimal("0")
    assert position.total_value == Decimal("100")


def test_yield_registry() -> None:
    class DemoAdapter(AbstractYieldAdapter):
        name = "demo"
        venue = YieldVenue.STAKING

        def get_opportunities(self, chain_id: str, token: str) -> list[YieldOpportunity]:
            return []

        def quote_deposit(
            self,
            position: YieldVenuePosition,
            amount: Decimal,
            opportunity: YieldOpportunity,
        ) -> Decimal:
            return position.principal + amount

        def quote_withdraw(
            self,
            position: YieldVenuePosition,
            amount: Decimal,
        ) -> tuple[Decimal, Decimal]:
            return position.principal - amount, position.rewards

        def harvest(self, position: YieldVenuePosition) -> YieldHarvest:
            return YieldHarvest(
                harvest_id="h1",
                position_id=position.position_id,
                agent_id=position.agent_id,
                amount=position.harvest(),
                venue=position.venue,
            )

    registry = YieldRegistry()
    adapter = DemoAdapter()
    registry.register("demo", adapter)
    assert "demo" in registry.list_adapters()
    assert registry.get("demo") is adapter

    with pytest.raises(KeyError):
        registry.get("missing")


def test_yield_opportunity_invalid_apy() -> None:
    with pytest.raises(ValueError):
        YieldOpportunity(
            venue=YieldVenue.STAKING,
            chain_id="ait-hub",
            token="AITBC",
            apy=Decimal("-1"),
            tvl=Decimal("1000"),
        )
