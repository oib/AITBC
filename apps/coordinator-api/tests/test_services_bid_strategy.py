"""Coverage for BidStrategyEngine math paths (#1289 residual).

The engine's initialize() spawns a market-monitor loop and its history
load is a stub; these tests pin the deterministic decision math —
strategy selection, bid parameter/price computation, success
probability, wait-time estimate, confidence, cost efficiency, trend
calculators, and market recommendations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from coordinator_api.contexts.trading.services.trading_market.bid_strategy import (
    BidStrategy,
    BidStrategyEngine,
    GPU_Tier,
    MarketConditions,
    TaskRequirements,
    UrgencyLevel,
)


@pytest.fixture
def engine() -> BidStrategyEngine:
    return BidStrategyEngine({})


def _conditions(**over) -> MarketConditions:
    base = {
        "current_gas_price": Decimal("20.0"),
        "gpu_utilization_rate": 0.75,
        "average_hourly_price": Decimal("0.05"),
        "price_volatility": 0.12,
        "demand_level": 0.68,
        "supply_level": 0.72,
        "timestamp": datetime.now(UTC),
    }
    base.update(over)
    return MarketConditions(**base)


def _task(**over) -> TaskRequirements:
    base = {
        "task_id": "t1",
        "agent_id": "a1",
        "urgency": UrgencyLevel.MEDIUM,
        "estimated_duration": 2.0,
        "gpu_tier": GPU_Tier.MID_RANGE_GPU,
        "memory_requirement": 8192,
        "compute_intensity": 0.5,
        "deadline": None,
        "max_budget": Decimal("10.0"),
        "priority_score": 0.5,
    }
    base.update(over)
    return TaskRequirements(**base)


# ---------------------------------------------------------------------------
# strategy selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_select_strategy_urgent(engine):
    s = await engine._select_optimal_strategy(_task(urgency=UrgencyLevel.CRITICAL), _conditions())
    assert s == BidStrategy.URGENT_BID


@pytest.mark.unit
async def test_select_strategy_low_budget(engine):
    s = await engine._select_optimal_strategy(_task(max_budget=Decimal("0.01")), _conditions())
    assert s == BidStrategy.COST_OPTIMIZED


async def test_select_strategy_high_volatility(engine):
    s = await engine._select_optimal_strategy(_task(), _conditions(price_volatility=0.5))
    assert s == BidStrategy.CONSERVATIVE


@pytest.mark.unit
async def test_select_strategy_preferred_boost(engine):
    await engine.update_agent_preferences("a1", {"preferred_strategy": "aggressive"})
    s = await engine._select_optimal_strategy(_task(), _conditions())
    # aggressive base 0.3*1.2=0.36 still loses to balanced 0.7 — pin current behavior
    assert s == BidStrategy.BALANCED


# ---------------------------------------------------------------------------
# bid parameters + price
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_bid_parameters_tier_and_strategy_multipliers(engine):
    p = await engine._calculate_bid_parameters(
        _task(gpu_tier=GPU_Tier.PREMIUM_GPU),
        _conditions(),
        BidStrategy.AGGRESSIVE,
        None,
    )
    assert p.tier_multiplier == Decimal("3.0")
    assert p.urgency_multiplier == Decimal("1.3")
    assert p.risk_premium == Decimal("0.25")
    assert p.base_price == Decimal("0.05")


@pytest.mark.unit
async def test_bid_parameters_market_premiums(engine):
    p = await engine._calculate_bid_parameters(
        _task(),
        _conditions(demand_level=0.9, supply_level=0.2, price_volatility=0.5),
        BidStrategy.BALANCED,
        None,
    )
    assert p.market_multiplier == Decimal("1.2") * Decimal("1.3") * Decimal("1.1")


@pytest.mark.unit
async def test_bid_parameters_deadline_time_factor(engine):
    soon = datetime.now(UTC) + timedelta(hours=1)
    p = await engine._calculate_bid_parameters(_task(deadline=soon), _conditions(), BidStrategy.BALANCED, None)
    assert p.time_factor == Decimal("1.5")
    far = datetime.now(UTC) + timedelta(hours=12)
    p2 = await engine._calculate_bid_parameters(_task(deadline=far), _conditions(), BidStrategy.BALANCED, None)
    assert p2.time_factor == Decimal("1.1")


@pytest.mark.unit
async def test_bid_price_capped_by_budget_rate(engine):
    # premium tier + aggressive on tight budget -> capped at max_budget/duration
    task = _task(gpu_tier=GPU_Tier.PREMIUM_GPU, max_budget=Decimal("0.02"), estimated_duration=2.0)
    price = await engine._calculate_bid_price(
        await engine._calculate_bid_parameters(task, _conditions(), BidStrategy.AGGRESSIVE, None),
        task,
    )
    assert price <= Decimal("0.01") + Decimal("0.000001")


@pytest.mark.unit
async def test_bid_price_floor(engine):
    task = _task(gpu_tier=GPU_Tier.CPU_ONLY, max_budget=Decimal("100"))
    price = await engine._calculate_bid_price(
        await engine._calculate_bid_parameters(task, _conditions(), BidStrategy.COST_OPTIMIZED, None),
        task,
    )
    assert price >= Decimal("0.001")


# ---------------------------------------------------------------------------
# scoring helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_success_probability_bounds(engine):
    prob = await engine._calculate_success_probability(Decimal("0.05"), _task(), _conditions())
    assert 0.1 <= prob <= 0.95


@pytest.mark.unit
async def test_wait_time_bounds_and_urgency(engine):
    w_crit = await engine._estimate_wait_time(Decimal("0.05"), _task(urgency=UrgencyLevel.CRITICAL), _conditions())
    w_low = await engine._estimate_wait_time(Decimal("0.05"), _task(urgency=UrgencyLevel.LOW), _conditions())
    assert w_crit < w_low
    assert w_crit >= 60


@pytest.mark.unit
async def test_confidence_bounds(engine):
    p = await engine._calculate_bid_parameters(_task(), _conditions(), BidStrategy.BALANCED, None)
    conf = await engine._calculate_confidence_score(p, _conditions(), BidStrategy.BALANCED)
    assert 0.3 <= conf <= 0.95


@pytest.mark.unit
async def test_cost_efficiency_bounds(engine):
    eff = await engine._calculate_cost_efficiency(Decimal("0.05"), _task(estimated_duration=2.0, max_budget=Decimal("1.0")))
    assert 0.1 <= eff <= 1.0


# ---------------------------------------------------------------------------
# trends + recommendations
# ---------------------------------------------------------------------------


def _seed_history(engine, n, price=0.05, demand=0.5, vol=0.1):
    now = datetime.now(UTC)
    engine.market_history = [
        _conditions(
            average_hourly_price=Decimal(str(price)),
            demand_level=demand,
            price_volatility=vol,
            timestamp=now - timedelta(hours=n - i),
        )
        for i in range(n)
    ]


@pytest.mark.unit
async def test_trends_insufficient_data(engine):
    _seed_history(engine, 10)
    assert await engine._calculate_price_trend() == "insufficient_data"
    assert await engine._calculate_demand_trend() == "insufficient_data"
    assert await engine._calculate_volatility_trend() == "insufficient_data"


@pytest.mark.unit
async def test_price_trend_increasing(engine):
    # 48 entries: older half at 0.04, recent half at 0.06
    now = datetime.now(UTC)
    engine.market_history = [
        _conditions(
            average_hourly_price=Decimal("0.04" if i < 24 else "0.06"),
            timestamp=now - timedelta(hours=48 - i),
        )
        for i in range(48)
    ]
    assert await engine._calculate_price_trend() == "increasing"


@pytest.mark.unit
async def test_demand_trend_decreasing(engine):
    now = datetime.now(UTC)
    engine.market_history = [
        _conditions(
            demand_level=0.9 if i < 24 else 0.3,
            timestamp=now - timedelta(hours=48 - i),
        )
        for i in range(48)
    ]
    assert await engine._calculate_demand_trend() == "decreasing"


@pytest.mark.unit
async def test_predict_market_conditions_short_history(engine):
    _seed_history(engine, 5)
    pred = await engine._predict_market_conditions(24)
    # insufficient history -> returns current conditions (stub: demand 0.68)
    assert pred.demand_level == pytest.approx(0.68)


@pytest.mark.unit
async def test_market_recommendations(engine):
    recs = await engine._generate_market_recommendations(
        _conditions(demand_level=0.9, price_volatility=0.5, gpu_utilization_rate=0.95, supply_level=0.2)
    )
    assert len(recs) >= 4


# ---------------------------------------------------------------------------
async def test_price_trend_zero_older_average(engine):
    now = datetime.now(UTC)
    engine.market_history = [
        _conditions(
            average_hourly_price=Decimal("0" if i < 24 else "0.05"),
            timestamp=now - timedelta(hours=48 - i),
        )
        for i in range(48)
    ]
    trend = await engine._calculate_price_trend()
    assert trend in {"increasing", "decreasing", "stable", "insufficient_data"}


async def test_invalid_preferred_strategy_does_not_crash(engine):
    await engine.update_agent_preferences("a1", {"preferred_strategy": "bogus"})
    result = await engine.calculate_bid(_task())
    assert result.bid_price > 0
