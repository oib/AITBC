"""Coverage for DynamicPricingEngine demand/supply multipliers (#1289 residual, #1363).

Pins the #1363 fix: _calculate_demand_multiplier is clamped to [0.5, 2.0]
like the supply multiplier — the low-band formula went negative for
demand_level < -2.0.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from coordinator_api.contexts.trading.services.trading_market.dynamic_pricing import (
    DynamicPricingEngine,
    PricingStrategy,
)


@pytest.fixture
def engine() -> DynamicPricingEngine:
    return DynamicPricingEngine({})


# ---------------------------------------------------------------------------
# Demand multiplier — #1363 clamp regression pins
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("strategy", list(PricingStrategy))
def test_demand_multiplier_never_negative(engine, strategy):
    # demand_level -3.0 -> low band 0.8 + (-3.0)*0.4 = -0.4 pre-fix.
    m = engine._calculate_demand_multiplier(-3.0, strategy)
    assert m >= Decimal("0.5")
    assert m <= Decimal("2.0")


@pytest.mark.unit
def test_demand_multiplier_normal_bands_unchanged(engine):
    # Band math preserved (float->Decimal carries binary noise; compare approx).
    assert float(engine._calculate_demand_multiplier(0.6, PricingStrategy.MARKET_BALANCE)) == pytest.approx(1.05)
    assert float(engine._calculate_demand_multiplier(0.9, PricingStrategy.MARKET_BALANCE)) == pytest.approx(1.25)
    assert float(engine._calculate_demand_multiplier(0.4, PricingStrategy.MARKET_BALANCE)) == pytest.approx(0.96)


@pytest.mark.unit
def test_supply_multiplier_still_clamped(engine):
    # supply_level extremes hit the [0.5, 2.0] bounds
    assert float(engine._calculate_supply_multiplier(-1.0, PricingStrategy.MARKET_BALANCE)) == pytest.approx(2.0)
    assert float(engine._calculate_supply_multiplier(3.0, PricingStrategy.MARKET_BALANCE)) == pytest.approx(0.5)
