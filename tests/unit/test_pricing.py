"""Unit tests for aitbc.agent_economics dynamic pricing (v0.12.0 §A4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    DemandForecast,
    DemandTrend,
    DynamicFeeMarket,
    MarketMakerStrategy,
    SurgePricing,
)


def test_market_maker_prices() -> None:
    strategy = MarketMakerStrategy(
        strategy_id="mm1",
        agent_id="agent-a",
        base_price=Decimal("100"),
        spread_percent=Decimal("2"),
    )
    assert strategy.bid_price() == Decimal("99.00")
    assert strategy.ask_price() == Decimal("101.00")
    assert strategy.mid_price() == Decimal("100.00")


def test_market_maker_inventory_adjustment() -> None:
    strategy = MarketMakerStrategy(
        strategy_id="mm1",
        agent_id="agent-a",
        base_price=Decimal("100"),
        spread_percent=Decimal("2"),
        inventory=Decimal("120"),
        max_position=Decimal("100"),
    )
    strategy.adjust_for_inventory()
    assert strategy.spread_percent == Decimal("2.20")


def test_surge_pricing_below_threshold() -> None:
    surge = SurgePricing(
        base_price=Decimal("10"),
        demand_threshold=Decimal("100"),
        max_multiplier=Decimal("5"),
    )
    surge.update(Decimal("50"))
    assert surge.price() == Decimal("10")


def test_surge_pricing_above_threshold() -> None:
    surge = SurgePricing(
        base_price=Decimal("10"),
        demand_threshold=Decimal("100"),
        max_multiplier=Decimal("3"),
    )
    surge.update(Decimal("250"))
    # extra = 150, threshold 100 -> multiplier = 1 + 1.5 = 2.5
    assert surge.current_multiplier == Decimal("2.5")
    assert surge.price() == Decimal("25")


def test_surge_pricing_capped() -> None:
    surge = SurgePricing(
        base_price=Decimal("10"),
        demand_threshold=Decimal("100"),
        max_multiplier=Decimal("2"),
    )
    surge.update(Decimal("500"))
    assert surge.current_multiplier == Decimal("2")


def test_demand_forecast_validation() -> None:
    with pytest.raises(ValueError):
        DemandForecast(
            forecast_id="f1",
            period="1h",
            predicted_demand=Decimal("-1"),
        )


def test_dynamic_fee_market_with_forecast() -> None:
    surge = SurgePricing(
        base_price=Decimal("10"),
        current_multiplier=Decimal("2"),
        demand_threshold=Decimal("100"),
        max_multiplier=Decimal("5"),
    )
    forecast = DemandForecast(
        forecast_id="f1",
        period="1h",
        predicted_demand=Decimal("200"),
        confidence=Decimal("0.5"),
        trend=DemandTrend.RISING,
    )
    market = DynamicFeeMarket(surge, forecast)
    assert market.fee() == Decimal("30")  # 10 * 2 * (1 + 0.5)


def test_dynamic_fee_market_flat() -> None:
    surge = SurgePricing(
        base_price=Decimal("10"),
        current_multiplier=Decimal("1.5"),
        demand_threshold=Decimal("100"),
        max_multiplier=Decimal("5"),
    )
    forecast = DemandForecast(
        forecast_id="f1",
        period="1h",
        predicted_demand=Decimal("120"),
        trend=DemandTrend.FLAT,
    )
    market = DynamicFeeMarket(surge, forecast)
    assert market.fee() == Decimal("15")
