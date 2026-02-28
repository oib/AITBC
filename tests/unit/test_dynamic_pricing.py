"""
Unit Tests for Dynamic Pricing Engine
Tests pricing calculations, strategies, and market data processing
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import numpy as np

from app.services.dynamic_pricing_engine import (
    DynamicPricingEngine,
    PricingStrategy,
    ResourceType,
    PriceConstraints,
    PricingFactors,
    MarketConditions,
    PriceTrend
)
from app.domain.pricing_strategies import StrategyLibrary


class TestDynamicPricingEngine:
    """Test cases for DynamicPricingEngine"""
    
    @pytest.fixture
    def pricing_engine(self):
        """Create a pricing engine instance for testing"""
        config = {
            "min_price": 0.001,
            "max_price": 1000.0,
            "update_interval": 300,
            "forecast_horizon": 72,
            "max_volatility_threshold": 0.3,
            "circuit_breaker_threshold": 0.5
        }
        engine = DynamicPricingEngine(config)
        return engine
    
    @pytest.fixture
    def sample_market_conditions(self):
        """Create sample market conditions for testing"""
        return MarketConditions(
            region="us_west",
            resource_type=ResourceType.GPU,
            demand_level=0.8,
            supply_level=0.6,
            average_price=0.05,
            price_volatility=0.15,
            utilization_rate=0.75,
            competitor_prices=[0.045, 0.055, 0.048, 0.052],
            market_sentiment=0.2
        )
    
    @pytest.mark.asyncio
    async def test_engine_initialization(self, pricing_engine):
        """Test engine initialization"""
        await pricing_engine.initialize()
        
        assert pricing_engine.min_price == 0.001
        assert pricing_engine.max_price == 1000.0
        assert pricing_engine.update_interval == 300
        assert pricing_engine.forecast_horizon == 72
        assert isinstance(pricing_engine.pricing_history, dict)
        assert isinstance(pricing_engine.provider_strategies, dict)
        assert isinstance(pricing_engine.price_constraints, dict)
    
    @pytest.mark.asyncio
    async def test_calculate_dynamic_price_basic(self, pricing_engine, sample_market_conditions):
        """Test basic dynamic price calculation"""
        
        # Mock market conditions
        with patch.object(pricing_engine, '_get_market_conditions', return_value=sample_market_conditions):
            result = await pricing_engine.calculate_dynamic_price(
                resource_id="test_gpu_1",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE,
                region="us_west"
            )
        
        assert result.resource_id == "test_gpu_1"
        assert result.resource_type == ResourceType.GPU
        assert result.current_price == 0.05
        assert result.recommended_price > 0
        assert result.recommended_price <= pricing_engine.max_price
        assert result.recommended_price >= pricing_engine.min_price
        assert isinstance(result.price_trend, PriceTrend)
        assert 0 <= result.confidence_score <= 1
        assert isinstance(result.factors_exposed, dict)
        assert isinstance(result.reasoning, list)
        assert result.strategy_used == PricingStrategy.MARKET_BALANCE
    
    @pytest.mark.asyncio
    async def test_pricing_strategies_different_results(self, pricing_engine, sample_market_conditions):
        """Test that different strategies produce different results"""
        
        with patch.object(pricing_engine, '_get_market_conditions', return_value=sample_market_conditions):
            # Test aggressive growth strategy
            result_growth = await pricing_engine.calculate_dynamic_price(
                resource_id="test_gpu_1",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.AGGRESSIVE_GROWTH,
                region="us_west"
            )
            
            # Test profit maximization strategy
            result_profit = await pricing_engine.calculate_dynamic_price(
                resource_id="test_gpu_1",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.PROFIT_MAXIMIZATION,
                region="us_west"
            )
            
            # Results should be different
            assert result_growth.recommended_price != result_profit.recommended_price
            assert result_growth.strategy_used == PricingStrategy.AGGRESSIVE_GROWTH
            assert result_profit.strategy_used == PricingStrategy.PROFIT_MAXIMIZATION
    
    @pytest.mark.asyncio
    async def test_price_constraints_application(self, pricing_engine, sample_market_conditions):
        """Test that price constraints are properly applied"""
        
        constraints = PriceConstraints(
            min_price=0.03,
            max_price=0.08,
            max_change_percent=0.2
        )
        
        with patch.object(pricing_engine, '_get_market_conditions', return_value=sample_market_conditions):
            result = await pricing_engine.calculate_dynamic_price(
                resource_id="test_gpu_1",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.PROFIT_MAXIMIZATION,
                constraints=constraints,
                region="us_west"
            )
        
        # Should respect constraints
        assert result.recommended_price >= constraints.min_price
        assert result.recommended_price <= constraints.max_price
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_activation(self, pricing_engine, sample_market_conditions):
        """Test circuit breaker activation during high volatility"""
        
        # Create high volatility conditions
        high_volatility_conditions = MarketConditions(
            region="us_west",
            resource_type=ResourceType.GPU,
            demand_level=0.9,
            supply_level=0.3,
            average_price=0.05,
            price_volatility=0.6,  # High volatility
            utilization_rate=0.95,
            competitor_prices=[0.045, 0.055, 0.048, 0.052],
            market_sentiment=-0.3
        )
        
        # Add some pricing history
        pricing_engine.pricing_history["test_gpu_1"] = [
            Mock(price=0.05, timestamp=datetime.utcnow() - timedelta(minutes=10))
        ]
        
        with patch.object(pricing_engine, '_get_market_conditions', return_value=high_volatility_conditions):
            result = await pricing_engine.calculate_dynamic_price(
                resource_id="test_gpu_1",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE,
                region="us_west"
            )
        
        # Circuit breaker should be activated
        assert "test_gpu_1" in pricing_engine.circuit_breakers
        assert pricing_engine.circuit_breakers["test_gpu_1"] is True
    
    @pytest.mark.asyncio
    async def test_price_forecast_generation(self, pricing_engine):
        """Test price forecast generation"""
        
        # Add historical data
        base_time = datetime.utcnow()
        for i in range(48):  # 48 data points
            pricing_engine.pricing_history["test_gpu_1"] = pricing_engine.pricing_history.get("test_gpu_1", [])
            pricing_engine.pricing_history["test_gpu_1"].append(
                Mock(
                    price=0.05 + (i * 0.001),
                    demand_level=0.6 + (i % 10) * 0.02,
                    supply_level=0.7 - (i % 8) * 0.01,
                    confidence=0.8,
                    strategy_used="market_balance",
                    timestamp=base_time - timedelta(hours=48-i)
                )
            )
        
        forecast = await pricing_engine.get_price_forecast("test_gpu_1", 24)
        
        assert len(forecast) == 24
        for point in forecast:
            assert hasattr(point, 'timestamp')
            assert hasattr(point, 'price')
            assert hasattr(point, 'demand_level')
            assert hasattr(point, 'supply_level')
            assert hasattr(point, 'confidence')
            assert 0 <= point.confidence <= 1
            assert point.price >= pricing_engine.min_price
            assert point.price <= pricing_engine.max_price
    
    @pytest.mark.asyncio
    async def test_provider_strategy_management(self, pricing_engine):
        """Test setting and retrieving provider strategies"""
        
        constraints = PriceConstraints(
            min_price=0.02,
            max_price=0.10
        )
        
        # Set strategy
        success = await pricing_engine.set_provider_strategy(
            provider_id="test_provider",
            strategy=PricingStrategy.AGGRESSIVE_GROWTH,
            constraints=constraints
        )
        
        assert success is True
        assert pricing_engine.provider_strategies["test_provider"] == PricingStrategy.AGGRESSIVE_GROWTH
        assert pricing_engine.price_constraints["test_provider"] == constraints
    
    def test_demand_multiplier_calculation(self, pricing_engine):
        """Test demand multiplier calculation"""
        
        # High demand
        multiplier_high = pricing_engine._calculate_demand_multiplier(0.9, PricingStrategy.MARKET_BALANCE)
        assert multiplier_high > 1.0
        
        # Low demand
        multiplier_low = pricing_engine._calculate_demand_multiplier(0.2, PricingStrategy.MARKET_BALANCE)
        assert multiplier_low < 1.0
        
        # Aggressive growth strategy should have lower multipliers
        multiplier_growth = pricing_engine._calculate_demand_multiplier(0.8, PricingStrategy.AGGRESSIVE_GROWTH)
        multiplier_balance = pricing_engine._calculate_demand_multiplier(0.8, PricingStrategy.MARKET_BALANCE)
        assert multiplier_growth < multiplier_balance
    
    def test_supply_multiplier_calculation(self, pricing_engine):
        """Test supply multiplier calculation"""
        
        # Low supply (should increase prices)
        multiplier_low_supply = pricing_engine._calculate_supply_multiplier(0.2, PricingStrategy.MARKET_BALANCE)
        assert multiplier_low_supply > 1.0
        
        # High supply (should decrease prices)
        multiplier_high_supply = pricing_engine._calculate_supply_multiplier(0.9, PricingStrategy.MARKET_BALANCE)
        assert multiplier_high_supply < 1.0
    
    def test_time_multiplier_calculation(self, pricing_engine):
        """Test time-based multiplier calculation"""
        
        # Test different hours
        business_hour_multiplier = pricing_engine._calculate_time_multiplier()
        
        # Mock different hours by temporarily changing the method
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.hour = 14  # 2 PM business hour
            business_hour_multiplier = pricing_engine._calculate_time_multiplier()
            assert business_hour_multiplier > 1.0
            
            mock_datetime.utcnow.return_value.hour = 3  # 3 AM late night
            late_night_multiplier = pricing_engine._calculate_time_multiplier()
            assert late_night_multiplier < 1.0
    
    def test_competition_multiplier_calculation(self, pricing_engine):
        """Test competition-based multiplier calculation"""
        
        competitor_prices = [0.045, 0.055, 0.048, 0.052]
        base_price = 0.05
        
        # Competitive response strategy
        multiplier_competitive = pricing_engine._calculate_competition_multiplier(
            base_price, competitor_prices, PricingStrategy.COMPETITIVE_RESPONSE
        )
        
        # Profit maximization strategy
        multiplier_profit = pricing_engine._calculate_competition_multiplier(
            base_price, competitor_prices, PricingStrategy.PROFIT_MAXIMIZATION
        )
        
        # Competitive strategy should be more responsive to competition
        assert isinstance(multiplier_competitive, float)
        assert isinstance(multiplier_profit, float)
    
    def test_price_trend_determination(self, pricing_engine):
        """Test price trend determination"""
        
        # Create increasing trend
        pricing_engine.pricing_history["test_resource"] = [
            Mock(price=0.05, timestamp=datetime.utcnow() - timedelta(minutes=50)),
            Mock(price=0.051, timestamp=datetime.utcnow() - timedelta(minutes=40)),
            Mock(price=0.052, timestamp=datetime.utcnow() - timedelta(minutes=30)),
            Mock(price=0.053, timestamp=datetime.utcnow() - timedelta(minutes=20)),
            Mock(price=0.054, timestamp=datetime.utcnow() - timedelta(minutes=10))
        ]
        
        trend = pricing_engine._determine_price_trend("test_resource", 0.055)
        assert trend == PriceTrend.INCREASING
        
        # Create decreasing trend
        pricing_engine.pricing_history["test_resource"] = [
            Mock(price=0.055, timestamp=datetime.utcnow() - timedelta(minutes=50)),
            Mock(price=0.054, timestamp=datetime.utcnow() - timedelta(minutes=40)),
            Mock(price=0.053, timestamp=datetime.utcnow() - timedelta(minutes=30)),
            Mock(price=0.052, timestamp=datetime.utcnow() - timedelta(minutes=20)),
            Mock(price=0.051, timestamp=datetime.utcnow() - timedelta(minutes=10))
        ]
        
        trend = pricing_engine._determine_price_trend("test_resource", 0.05)
        assert trend == PriceTrend.DECREASING
    
    def test_confidence_score_calculation(self, pricing_engine, sample_market_conditions):
        """Test confidence score calculation"""
        
        factors = PricingFactors(
            base_price=0.05,
            demand_level=0.8,
            supply_level=0.6,
            market_volatility=0.1,
            confidence_score=0.8
        )
        
        confidence = pricing_engine._calculate_confidence_score(factors, sample_market_conditions)
        
        assert 0 <= confidence <= 1
        assert isinstance(confidence, float)
    
    def test_pricing_factors_calculation(self, pricing_engine, sample_market_conditions):
        """Test pricing factors calculation"""
        
        factors = asyncio.run(pricing_engine._calculate_pricing_factors(
            resource_id="test_gpu_1",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE,
            market_conditions=sample_market_conditions
        ))
        
        assert isinstance(factors, PricingFactors)
        assert factors.base_price == 0.05
        assert 0 <= factors.demand_multiplier <= 3.0
        assert 0.8 <= factors.supply_multiplier <= 2.5
        assert 0.7 <= factors.time_multiplier <= 1.5
        assert 0.9 <= factors.performance_multiplier <= 1.3
        assert 0.8 <= factors.competition_multiplier <= 1.4
        assert 0.9 <= factors.sentiment_multiplier <= 1.2
        assert 0.8 <= factors.regional_multiplier <= 1.3
    
    def test_strategy_pricing_application(self, pricing_engine, sample_market_conditions):
        """Test strategy-specific pricing application"""
        
        factors = PricingFactors(
            base_price=0.05,
            demand_multiplier=1.2,
            supply_multiplier=1.1,
            time_multiplier=1.0,
            performance_multiplier=1.05,
            competition_multiplier=0.95,
            sentiment_multiplier=1.02,
            regional_multiplier=1.0
        )
        
        # Test different strategies
        price_aggressive = asyncio.run(pricing_engine._apply_strategy_pricing(
            0.05, factors, PricingStrategy.AGGRESSIVE_GROWTH, sample_market_conditions
        ))
        
        price_profit = asyncio.run(pricing_engine._apply_strategy_pricing(
            0.05, factors, PricingStrategy.PROFIT_MAXIMIZATION, sample_market_conditions
        ))
        
        # Should produce different results
        assert price_aggressive != price_profit
        assert price_aggressive > 0
        assert price_profit > 0
    
    def test_constraints_and_risk_application(self, pricing_engine):
        """Test constraints and risk management application"""
        
        constraints = PriceConstraints(
            min_price=0.03,
            max_price=0.08,
            max_change_percent=0.2
        )
        
        factors = PricingFactors(
            base_price=0.05,
            market_volatility=0.1
        )
        
        # Test normal price within constraints
        normal_price = asyncio.run(pricing_engine._apply_constraints_and_risk(
            "test_resource", 0.06, constraints, factors
        ))
        assert 0.03 <= normal_price <= 0.08
        
        # Test price above max constraint
        high_price = asyncio.run(pricing_engine._apply_constraints_and_risk(
            "test_resource", 0.10, constraints, factors
        ))
        assert high_price <= constraints.max_price
        
        # Test price below min constraint
        low_price = asyncio.run(pricing_engine._apply_constraints_and_risk(
            "test_resource", 0.01, constraints, factors
        ))
        assert low_price >= constraints.min_price
    
    def test_price_point_storage(self, pricing_engine):
        """Test price point storage in history"""
        
        factors = PricingFactors(
            base_price=0.05,
            demand_level=0.8,
            supply_level=0.6,
            confidence_score=0.85
        )
        
        asyncio.run(pricing_engine._store_price_point(
            "test_resource", 0.055, factors, PricingStrategy.MARKET_BALANCE
        ))
        
        assert "test_resource" in pricing_engine.pricing_history
        assert len(pricing_engine.pricing_history["test_resource"]) == 1
        
        point = pricing_engine.pricing_history["test_resource"][0]
        assert point.price == 0.055
        assert point.demand_level == 0.8
        assert point.supply_level == 0.6
        assert point.confidence == 0.85
        assert point.strategy_used == "market_balance"
    
    def test_seasonal_factor_calculation(self, pricing_engine):
        """Test seasonal factor calculation"""
        
        # Test morning hours
        morning_factor = pricing_engine._calculate_seasonal_factor(9)
        assert morning_factor > 1.0
        
        # Test business peak
        peak_factor = pricing_engine._calculate_seasonal_factor(14)
        assert peak_factor > morning_factor
        
        # Test late night
        night_factor = pricing_engine._calculate_seasonal_factor(3)
        assert night_factor < 1.0
    
    def test_demand_supply_forecasting(self, pricing_engine):
        """Test demand and supply level forecasting"""
        
        demand_history = [0.6, 0.7, 0.8, 0.75, 0.9, 0.85]
        supply_history = [0.7, 0.6, 0.5, 0.55, 0.4, 0.45]
        
        demand_forecast = pricing_engine._forecast_demand_level(demand_history, 1)
        supply_forecast = pricing_engine._forecast_supply_level(supply_history, 1)
        
        assert 0 <= demand_forecast <= 1
        assert 0 <= supply_forecast <= 1
        assert isinstance(demand_forecast, float)
        assert isinstance(supply_forecast, float)


class TestPricingFactors:
    """Test cases for PricingFactors dataclass"""
    
    def test_pricing_factors_creation(self):
        """Test PricingFactors creation with default values"""
        factors = PricingFactors(base_price=0.05)
        
        assert factors.base_price == 0.05
        assert factors.demand_multiplier == 1.0
        assert factors.supply_multiplier == 1.0
        assert factors.time_multiplier == 1.0
        assert factors.performance_multiplier == 1.0
        assert factors.competition_multiplier == 1.0
        assert factors.sentiment_multiplier == 1.0
        assert factors.regional_multiplier == 1.0
        assert factors.confidence_score == 0.8
        assert factors.risk_adjustment == 0.0
    
    def test_pricing_factors_with_custom_values(self):
        """Test PricingFactors creation with custom values"""
        factors = PricingFactors(
            base_price=0.05,
            demand_multiplier=1.5,
            supply_multiplier=0.8,
            confidence_score=0.9
        )
        
        assert factors.base_price == 0.05
        assert factors.demand_multiplier == 1.5
        assert factors.supply_multiplier == 0.8
        assert factors.confidence_score == 0.9


class TestPriceConstraints:
    """Test cases for PriceConstraints dataclass"""
    
    def test_price_constraints_creation(self):
        """Test PriceConstraints creation with default values"""
        constraints = PriceConstraints()
        
        assert constraints.min_price is None
        assert constraints.max_price is None
        assert constraints.max_change_percent == 0.5
        assert constraints.min_change_interval == 300
        assert constraints.strategy_lock_period == 3600
    
    def test_price_constraints_with_custom_values(self):
        """Test PriceConstraints creation with custom values"""
        constraints = PriceConstraints(
            min_price=0.02,
            max_price=0.10,
            max_change_percent=0.3
        )
        
        assert constraints.min_price == 0.02
        assert constraints.max_price == 0.10
        assert constraints.max_change_percent == 0.3


class TestMarketConditions:
    """Test cases for MarketConditions dataclass"""
    
    def test_market_conditions_creation(self):
        """Test MarketConditions creation"""
        conditions = MarketConditions(
            region="us_west",
            resource_type=ResourceType.GPU,
            demand_level=0.8,
            supply_level=0.6,
            average_price=0.05,
            price_volatility=0.15,
            utilization_rate=0.75
        )
        
        assert conditions.region == "us_west"
        assert conditions.resource_type == ResourceType.GPU
        assert conditions.demand_level == 0.8
        assert conditions.supply_level == 0.6
        assert conditions.average_price == 0.05
        assert conditions.price_volatility == 0.15
        assert conditions.utilization_rate == 0.75
        assert conditions.competitor_prices == []
        assert conditions.market_sentiment == 0.0
        assert isinstance(conditions.timestamp, datetime)


class TestStrategyLibrary:
    """Test cases for StrategyLibrary"""
    
    def test_get_all_strategies(self):
        """Test getting all available strategies"""
        strategies = StrategyLibrary.get_all_strategies()
        
        assert isinstance(strategies, dict)
        assert len(strategies) > 0
        assert PricingStrategy.AGGRESSIVE_GROWTH in strategies
        assert PricingStrategy.PROFIT_MAXIMIZATION in strategies
        assert PricingStrategy.MARKET_BALANCE in strategies
        
        # Check strategy configurations
        for strategy_type, config in strategies.items():
            assert config.strategy_type == strategy_type
            assert config.name is not None
            assert config.description is not None
            assert config.parameters is not None
            assert isinstance(config.parameters.base_multiplier, float)
    
    def test_aggressive_growth_strategy(self):
        """Test aggressive growth strategy configuration"""
        strategy = StrategyLibrary.get_aggressive_growth_strategy()
        
        assert strategy.strategy_type == PricingStrategy.AGGRESSIVE_GROWTH
        assert strategy.parameters.base_multiplier < 1.0  # Lower prices for growth
        assert strategy.parameters.growth_target_rate > 0.2  # High growth target
        assert strategy.risk_tolerance.value == "aggressive"
    
    def test_profit_maximization_strategy(self):
        """Test profit maximization strategy configuration"""
        strategy = StrategyLibrary.get_profit_maximization_strategy()
        
        assert strategy.strategy_type == PricingStrategy.PROFIT_MAXIMIZATION
        assert strategy.parameters.base_multiplier > 1.0  # Higher prices for profit
        assert strategy.parameters.profit_target_margin > 0.3  # High profit target
        assert strategy.parameters.demand_sensitivity > 0.5  # Demand sensitive
    
    def test_market_balance_strategy(self):
        """Test market balance strategy configuration"""
        strategy = StrategyLibrary.get_market_balance_strategy()
        
        assert strategy.strategy_type == PricingStrategy.MARKET_BALANCE
        assert strategy.parameters.base_multiplier == 1.0  # Balanced pricing
        assert strategy.parameters.volatility_threshold < 0.2  # Lower volatility tolerance
        assert strategy.risk_tolerance.value == "moderate"


if __name__ == "__main__":
    pytest.main([__file__])
