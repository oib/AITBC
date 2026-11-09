"""Coverage for DynamicPricingEngine math helpers (#1289 residual).

The engine's initialize() path does file I/O and spawns background
loops; these tests pin the pure pricing-math helpers that decide actual
price multipliers — demand/supply/competition/sentiment/regional/
seasonal factors, trend slope, and the forecast clamps.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from coordinator_api.contexts.trading.services.trading_market.dynamic_pricing import (
    DynamicPricingEngine,
    PricingStrategy,
    ResourceType,
    _D,
    _serialize_decimals,
)


@pytest.fixture
def engine() -> DynamicPricingEngine:
    return DynamicPricingEngine({})


# ---------------------------------------------------------------------------
# module helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_D_converts_types():
    assert _D(1) == Decimal("1")
    assert _D("1.5") == Decimal("1.5")
    assert _D(1.5) == Decimal("1.5")
    d = Decimal("2.5")
    assert _D(d) is d


@pytest.mark.unit
def test_serialize_decimals():
    out = _serialize_decimals({"a": Decimal("1.5"), "b": 2, "c": "x"})
    assert out == {"a": "1.5", "b": 2, "c": "x"}


# ---------------------------------------------------------------------------
# demand multiplier
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_demand_multiplier_high_demand(engine):
    # demand 0.9 -> 1 + 0.1*2.5 = 1.25
    m = engine._calculate_demand_multiplier(0.9, PricingStrategy.MARKET_BALANCE)
    assert m == Decimal("1.25")


@pytest.mark.unit
def test_demand_multiplier_mid_band(engine):
    # demand 0.6 -> 1 + 0.1*0.5 = 1.05
    m = engine._calculate_demand_multiplier(0.6, PricingStrategy.MARKET_BALANCE)
    assert m == Decimal("1.05")


@pytest.mark.unit
def test_demand_multiplier_low_band(engine):
    # demand 0.25 -> 0.8 + 0.25*0.4 = 0.9
    m = engine._calculate_demand_multiplier(0.25, PricingStrategy.MARKET_BALANCE)
    assert m == Decimal("0.9")


@pytest.mark.unit
def test_demand_multiplier_strategy_modifiers(engine):
    base = engine._calculate_demand_multiplier(0.9, PricingStrategy.MARKET_BALANCE)
    aggressive = engine._calculate_demand_multiplier(0.9, PricingStrategy.AGGRESSIVE_GROWTH)
    profit = engine._calculate_demand_multiplier(0.9, PricingStrategy.PROFIT_MAXIMIZATION)
    assert aggressive == _D(float(base) * 0.9)
    assert profit == _D(float(base) * 1.3)


# ---------------------------------------------------------------------------
# supply / competition / sentiment / regional / seasonal
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_supply_multiplier_bounds(engine):
    # extreme scarcity and surplus both clamp into [0.5, 2.0]
    assert engine._calculate_supply_multiplier(0.0, PricingStrategy.MARKET_BALANCE) <= Decimal("2.0")
    assert engine._calculate_supply_multiplier(1.0, PricingStrategy.MARKET_BALANCE) >= Decimal("0.5")


@pytest.mark.unit
def test_supply_multiplier_scarcity_premium(engine):
    scarce = engine._calculate_supply_multiplier(0.1, PricingStrategy.MARKET_BALANCE)
    abundant = engine._calculate_supply_multiplier(0.9, PricingStrategy.MARKET_BALANCE)
    assert scarce > abundant


@pytest.mark.unit
def test_competition_multiplier_no_competitors(engine):
    assert engine._calculate_competition_multiplier(Decimal("1.0"), [], PricingStrategy.MARKET_BALANCE) == Decimal("1.0")


@pytest.mark.unit
def test_competition_multiplier_below_market(engine):
    # base 0.9 vs competitors at 1.0 -> ratio 0.9 -> market_balance: 1 + (0.9-1)*0.5 = 0.95
    m = engine._calculate_competition_multiplier(Decimal("0.9"), [Decimal("1.0")], PricingStrategy.MARKET_BALANCE)
    assert m == Decimal("0.95")


@pytest.mark.unit
def test_competitive_response_branches(engine):
    # price_ratio > 1.1 -> 0.9 ; < 0.9 -> 1.05 ; else 1.0
    assert engine._calculate_competition_multiplier(
        Decimal("1.2"), [Decimal("1.0")], PricingStrategy.COMPETITIVE_RESPONSE
    ) == Decimal("0.9")
    assert engine._calculate_competition_multiplier(
        Decimal("0.8"), [Decimal("1.0")], PricingStrategy.COMPETITIVE_RESPONSE
    ) == Decimal("1.05")
    assert engine._calculate_competition_multiplier(
        Decimal("1.0"), [Decimal("1.0")], PricingStrategy.COMPETITIVE_RESPONSE
    ) == Decimal("1.0")


@pytest.mark.unit
def test_sentiment_multiplier(engine):
    assert engine._calculate_sentiment_multiplier(0.5) == Decimal("1.1")
    assert engine._calculate_sentiment_multiplier(-0.5) == Decimal("0.9")
    assert engine._calculate_sentiment_multiplier(0.0) == Decimal("1.0")


@pytest.mark.unit
def test_regional_multiplier(engine):
    assert engine._calculate_regional_multiplier("us_east", ResourceType.GPU) == Decimal("1.2")
    assert engine._calculate_regional_multiplier("asia", ResourceType.GPU) == Decimal("0.9")
    assert engine._calculate_regional_multiplier("unknown", ResourceType.GPU) == Decimal("1.0")


@pytest.mark.unit
def test_seasonal_factor(engine):
    assert engine._calculate_seasonal_factor(8) == Decimal("1.05")
    assert engine._calculate_seasonal_factor(12) == Decimal("1.1")
    assert engine._calculate_seasonal_factor(22) == Decimal("0.95")
    assert engine._calculate_seasonal_factor(2) == Decimal("0.9")


# ---------------------------------------------------------------------------
# trend / forecasts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_price_trend_slope(engine):
    assert engine._calculate_price_trend([1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert engine._calculate_price_trend([3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    assert engine._calculate_price_trend([1.0]) == 0.0
    assert engine._calculate_price_trend([]) == 0.0


@pytest.mark.unit
def test_forecast_empty_defaults(engine):
    assert engine._forecast_demand_level([], 1) == pytest.approx(0.5, abs=0.2)
    assert engine._forecast_supply_level([], 1) == pytest.approx(0.5, abs=0.2)


@pytest.mark.unit
def test_forecast_clamped_to_unit_interval(engine):
    # extreme history must still clamp into [0, 1]
    for _ in range(20):
        d = engine._forecast_demand_level([0.99] * 10, 1)
        s = engine._forecast_supply_level([0.99] * 20, 1)
        assert 0.0 <= d <= 1.0
        assert 0.0 <= s <= 1.0


@pytest.mark.unit
def test_forecasts_are_deterministic(engine):
    # #1375 residual: forecast helpers must not inject np.random noise —
    # same history in, same forecast out.
    history = [0.4, 0.5, 0.6, 0.55]
    assert engine._forecast_demand_level(history, 3) == engine._forecast_demand_level(history, 3)
    assert engine._forecast_supply_level(history, 3) == engine._forecast_supply_level(history, 3)
    assert engine._forecast_demand_level(history, 3) == pytest.approx(sum(history) / len(history))


# ---------------------------------------------------------------------------
# demand multiplier floor — #1363 clamp regression pin (was strict-xfail pre-fix)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("strategy", list(PricingStrategy))
def test_demand_multiplier_never_negative(engine, strategy):
    # demand_level -3.0 -> low band 0.8 + (-3.0)*0.4 = -0.4 pre-#1363-fix.
    m = engine._calculate_demand_multiplier(-3.0, strategy)
    assert m >= Decimal("0.5")
    assert m <= Decimal("2.0")


# ---------------------------------------------------------------------------
# #1375 market conditions — real listings or honest neutral, never random
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_market_conditions_neutral_for_non_gpu(engine):
    """Non-GPU resource types get deterministic neutral conditions."""
    cond = await engine._load_market_conditions(ResourceType.SERVICE, "global")
    assert cond.demand_level == 0.5
    assert cond.supply_level == 0.5
    assert cond.utilization_rate == 0.5
    assert cond.price_volatility == 0.0
    assert cond.competitor_prices == []
    assert cond.market_sentiment == 0.0
    # Deterministic: a second call returns identical values (no random walk).
    again = await engine._load_market_conditions(ResourceType.STORAGE, "eu")
    assert again.demand_level == cond.demand_level
    assert again.supply_level == cond.supply_level


@pytest.mark.unit
async def test_market_conditions_gpu_snapshot_from_listings(engine, monkeypatch):
    """GPU conditions derive from live GPURegistry rows, not np.random."""
    import coordinator_api.storage.db as dbmod

    class _Gpu:
        def __init__(self, status, price):
            self.status = status
            self.price_per_hour = price

    rows = [_Gpu("available", Decimal("0.05")), _Gpu("available", Decimal("0.05")), _Gpu("booked", Decimal("0.07"))]

    class _Scalars:
        def all(self):
            return rows

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, stmt):
            return _Result()

    monkeypatch.setattr(dbmod, "session_scope", lambda: _Session())
    cond = await engine._load_market_conditions(ResourceType.GPU, "global")
    assert cond.supply_level == pytest.approx(2 / 3)
    assert cond.utilization_rate == pytest.approx(1 / 3)
    assert cond.average_price == Decimal("0.06")
    assert cond.competitor_prices == [Decimal("0.05"), Decimal("0.07")]
    assert cond.demand_level == 0.5
    assert cond.market_sentiment == 0.0


@pytest.mark.unit
async def test_market_conditions_gpu_empty_falls_back_neutral(engine, monkeypatch):
    """No active listings -> neutral conditions, not fabricated prices."""
    import coordinator_api.storage.db as dbmod

    class _Scalars:
        def all(self):
            return []

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, stmt):
            return _Result()

    monkeypatch.setattr(dbmod, "session_scope", lambda: _Session())
    cond = await engine._load_market_conditions(ResourceType.GPU, "global")
    assert cond.supply_level == 0.5
    assert cond.competitor_prices == []
    assert cond.average_price == Decimal("0")
