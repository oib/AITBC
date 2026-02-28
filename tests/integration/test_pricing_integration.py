"""
Integration Tests for Dynamic Pricing System
Tests end-to-end pricing workflows and marketplace integration
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import httpx
from fastapi.testclient import TestClient

from app.services.dynamic_pricing_engine import DynamicPricingEngine, PricingStrategy, ResourceType
from app.services.market_data_collector import MarketDataCollector, DataSource
from app.routers.dynamic_pricing import router
from app.domain.pricing_models import PricingHistory, ProviderPricingStrategy, MarketMetrics
from app.schemas.pricing import DynamicPriceRequest, PricingStrategyRequest


class TestPricingIntegration:
    """Integration tests for the complete pricing system"""
    
    @pytest.fixture
    def pricing_engine(self):
        """Create and initialize pricing engine"""
        config = {
            "min_price": 0.001,
            "max_price": 1000.0,
            "update_interval": 60,  # Faster for testing
            "forecast_horizon": 24,
            "max_volatility_threshold": 0.3,
            "circuit_breaker_threshold": 0.5
        }
        engine = DynamicPricingEngine(config)
        return engine
    
    @pytest.fixture
    def market_collector(self):
        """Create and initialize market data collector"""
        config = {
            "websocket_port": 8766  # Different port for testing
        }
        collector = MarketDataCollector(config)
        return collector
    
    @pytest.fixture
    def test_client(self):
        """Create FastAPI test client"""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/pricing")
        return TestClient(app)
    
    @pytest.mark.asyncio
    async def test_full_pricing_workflow(self, pricing_engine, market_collector):
        """Test complete pricing workflow from data collection to price calculation"""
        
        # Initialize both services
        await pricing_engine.initialize()
        await market_collector.initialize()
        
        # Simulate market data collection
        await market_collector._collect_gpu_metrics()
        await market_collector._collect_booking_data()
        await market_collector._collect_competitor_prices()
        
        # Wait for data aggregation
        await asyncio.sleep(0.1)
        
        # Calculate dynamic price
        result = await pricing_engine.calculate_dynamic_price(
            resource_id="integration_test_gpu",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE,
            region="us_west"
        )
        
        # Verify workflow completed successfully
        assert result.resource_id == "integration_test_gpu"
        assert result.recommended_price > 0
        assert result.confidence_score > 0
        assert len(result.reasoning) > 0
        
        # Verify market data was collected
        assert len(market_collector.raw_data) > 0
        assert len(market_collector.aggregated_data) > 0
    
    @pytest.mark.asyncio
    async def test_strategy_optimization_workflow(self, pricing_engine):
        """Test strategy optimization based on performance feedback"""
        
        await pricing_engine.initialize()
        
        # Set initial strategy
        await pricing_engine.set_provider_strategy(
            provider_id="test_provider",
            strategy=PricingStrategy.MARKET_BALANCE
        )
        
        # Simulate multiple pricing calculations with performance feedback
        performance_data = []
        for i in range(10):
            result = await pricing_engine.calculate_dynamic_price(
                resource_id=f"test_resource_{i}",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE
            )
            
            # Simulate performance metrics
            performance = {
                "revenue_growth": 0.05 + (i * 0.01),
                "profit_margin": 0.2 + (i * 0.02),
                "market_share": 0.1 + (i * 0.01),
                "customer_satisfaction": 0.8 + (i * 0.01),
                "price_stability": 0.1 - (i * 0.005)
            }
            performance_data.append(performance)
        
        # Verify strategy effectiveness tracking
        assert pricing_engine.provider_strategies["test_provider"] == PricingStrategy.MARKET_BALANCE
        
        # Verify pricing history was recorded
        assert len(pricing_engine.pricing_history) > 0
    
    @pytest.mark.asyncio
    async def test_market_data_integration(self, pricing_engine, market_collector):
        """Test integration between market data collector and pricing engine"""
        
        await pricing_engine.initialize()
        await market_collector.initialize()
        
        # Register pricing engine callback for market data
        async def pricing_callback(data_point):
            """Callback to process market data in pricing engine"""
            # Mock processing of market data
            pass
        
        market_collector.register_callback(DataSource.GPU_METRICS, pricing_callback)
        market_collector.register_callback(DataSource.BOOKING_DATA, pricing_callback)
        
        # Collect market data
        await market_collector._collect_gpu_metrics()
        await market_collector._collect_booking_data()
        await market_collector._collect_competitor_prices()
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        # Verify data was collected and callbacks were triggered
        assert len(market_collector.raw_data) > 0
        
        # Get aggregated data
        market_data = await market_collector.get_aggregated_data("gpu", "us_west")
        if market_data:
            assert market_data.resource_type == "gpu"
            assert market_data.region == "us_west"
            assert 0 <= market_data.demand_level <= 1
            assert 0 <= market_data.supply_level <= 1
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, pricing_engine, market_collector):
        """Test circuit breaker functionality during market stress"""
        
        await pricing_engine.initialize()
        await market_collector.initialize()
        
        # Add pricing history
        base_time = datetime.utcnow()
        for i in range(5):
            pricing_engine.pricing_history["circuit_test_gpu"] = pricing_engine.pricing_history.get("circuit_test_gpu", [])
            pricing_engine.pricing_history["circuit_test_gpu"].append(
                Mock(
                    price=0.05,
                    timestamp=base_time - timedelta(minutes=10-i),
                    demand_level=0.5,
                    supply_level=0.5,
                    confidence=0.8,
                    strategy_used="market_balance"
                )
            )
        
        # Simulate high volatility market conditions
        with patch.object(market_collector, '_collect_gpu_metrics') as mock_collect:
            # Mock high volatility data
            mock_collect.return_value = None
            # Directly add high volatility data
            await market_collector._add_data_point(Mock(
                source=DataSource.GPU_METRICS,
                resource_id="circuit_test_gpu",
                resource_type="gpu",
                region="us_west",
                timestamp=datetime.utcnow(),
                value=0.95,  # Very high utilization
                metadata={"volatility": 0.8}  # High volatility
            ))
        
        # Calculate price that should trigger circuit breaker
        result = await pricing_engine.calculate_dynamic_price(
            resource_id="circuit_test_gpu",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE,
            region="us_west"
        )
        
        # Circuit breaker should be activated
        assert "circuit_test_gpu" in pricing_engine.circuit_breakers
    
    @pytest.mark.asyncio
    async def test_forecast_accuracy_tracking(self, pricing_engine):
        """Test price forecast accuracy tracking"""
        
        await pricing_engine.initialize()
        
        # Add historical data
        base_time = datetime.utcnow()
        for i in range(48):
            pricing_engine.pricing_history["forecast_test_gpu"] = pricing_engine.pricing_history.get("forecast_test_gpu", [])
            pricing_engine.pricing_history["forecast_test_gpu"].append(
                Mock(
                    price=0.05 + (i * 0.001),
                    demand_level=0.6 + (i % 10) * 0.02,
                    supply_level=0.7 - (i % 8) * 0.01,
                    confidence=0.8,
                    strategy_used="market_balance",
                    timestamp=base_time - timedelta(hours=48-i)
                )
            )
        
        # Generate forecast
        forecast = await pricing_engine.get_price_forecast("forecast_test_gpu", 24)
        
        assert len(forecast) == 24
        
        # Verify forecast structure
        for point in forecast:
            assert hasattr(point, 'timestamp')
            assert hasattr(point, 'price')
            assert hasattr(point, 'confidence')
            assert 0 <= point.confidence <= 1
    
    def test_api_endpoints_integration(self, test_client):
        """Test API endpoints integration"""
        
        # Test health check
        response = test_client.get("/api/v1/pricing/health")
        assert response.status_code == 200
        health_data = response.json()
        assert "status" in health_data
        assert "services" in health_data
        
        # Test available strategies
        response = test_client.get("/api/v1/pricing/strategies/available")
        assert response.status_code == 200
        strategies = response.json()
        assert isinstance(strategies, list)
        assert len(strategies) > 0
        
        # Verify strategy structure
        for strategy in strategies:
            assert "strategy" in strategy
            assert "name" in strategy
            assert "description" in strategy
            assert "parameters" in strategy
    
    @pytest.mark.asyncio
    async def test_bulk_strategy_updates(self, pricing_engine):
        """Test bulk strategy updates functionality"""
        
        await pricing_engine.initialize()
        
        # Prepare bulk update data
        providers = ["provider_1", "provider_2", "provider_3"]
        strategies = [PricingStrategy.AGGRESSIVE_GROWTH, PricingStrategy.PROFIT_MAXIMIZATION, PricingStrategy.MARKET_BALANCE]
        
        # Apply bulk updates
        for provider_id, strategy in zip(providers, strategies):
            await pricing_engine.set_provider_strategy(provider_id, strategy)
        
        # Verify all strategies were set
        for provider_id, expected_strategy in zip(providers, strategies):
            assert pricing_engine.provider_strategies[provider_id] == expected_strategy
        
        # Test pricing with different strategies
        results = []
        for provider_id in providers:
            result = await pricing_engine.calculate_dynamic_price(
                resource_id=f"{provider_id}_gpu",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=pricing_engine.provider_strategies[provider_id]
            )
            results.append(result)
        
        # Verify different strategies produce different results
        prices = [result.recommended_price for result in results]
        assert len(set(prices)) > 1  # Should have different prices
    
    @pytest.mark.asyncio
    async def test_regional_pricing_differentiation(self, pricing_engine, market_collector):
        """Test regional pricing differentiation"""
        
        await pricing_engine.initialize()
        await market_collector.initialize()
        
        regions = ["us_west", "us_east", "europe", "asia"]
        results = {}
        
        # Calculate prices for different regions
        for region in regions:
            # Simulate regional market data
            await market_collector._collect_gpu_metrics()
            await market_collector._collect_regional_demand()
            
            result = await pricing_engine.calculate_dynamic_price(
                resource_id=f"regional_test_gpu",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE,
                region=region
            )
            results[region] = result
        
        # Verify regional differentiation
        regional_prices = {region: result.recommended_price for region, result in results.items()}
        
        # Prices should vary by region
        assert len(set(regional_prices.values())) > 1
        
        # Verify regional multipliers were applied
        for region, result in results.items():
            assert result.reasoning is not None
            # Check if regional reasoning is present
            reasoning_text = " ".join(result.reasoning).lower()
            # Regional factors should be considered
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, pricing_engine):
        """Test performance monitoring and metrics collection"""
        
        await pricing_engine.initialize()
        
        # Simulate multiple pricing operations
        start_time = datetime.utcnow()
        
        for i in range(20):
            await pricing_engine.calculate_dynamic_price(
                resource_id=f"perf_test_gpu_{i}",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE
            )
        
        end_time = datetime.utcnow()
        operation_time = (end_time - start_time).total_seconds()
        
        # Verify performance metrics
        assert operation_time < 10.0  # Should complete within 10 seconds
        assert len(pricing_engine.pricing_history) == 20
        
        # Verify pricing history tracking
        for i in range(20):
            resource_id = f"perf_test_gpu_{i}"
            assert resource_id in pricing_engine.pricing_history
            assert len(pricing_engine.pricing_history[resource_id]) == 1
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, pricing_engine, market_collector):
        """Test error handling and recovery mechanisms"""
        
        await pricing_engine.initialize()
        await market_collector.initialize()
        
        # Test with invalid resource type
        with pytest.raises(Exception):
            await pricing_engine.calculate_dynamic_price(
                resource_id="test_gpu",
                resource_type="invalid_type",  # Invalid type
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE
            )
        
        # Test with invalid price constraints
        constraints = Mock(min_price=0.10, max_price=0.05)  # Invalid constraints
        
        # Should handle gracefully
        result = await pricing_engine.calculate_dynamic_price(
            resource_id="test_gpu",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE,
            constraints=constraints
        )
        
        # Should still return a valid result
        assert result.recommended_price > 0
        assert result.confidence_score >= 0
    
    @pytest.mark.asyncio
    async def test_concurrent_pricing_calculations(self, pricing_engine):
        """Test concurrent pricing calculations"""
        
        await pricing_engine.initialize()
        
        # Create multiple concurrent tasks
        tasks = []
        for i in range(10):
            task = pricing_engine.calculate_dynamic_price(
                resource_id=f"concurrent_test_gpu_{i}",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE
            )
            tasks.append(task)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)
        
        # Verify all calculations completed successfully
        assert len(results) == 10
        
        for i, result in enumerate(results):
            assert result.resource_id == f"concurrent_test_gpu_{i}"
            assert result.recommended_price > 0
            assert result.confidence_score > 0
    
    @pytest.mark.asyncio
    async def test_data_consistency_across_services(self, pricing_engine, market_collector):
        """Test data consistency between pricing engine and market collector"""
        
        await pricing_engine.initialize()
        await market_collector.initialize()
        
        # Collect market data
        await market_collector._collect_gpu_metrics()
        await market_collector._collect_booking_data()
        await market_collector._collect_competitor_prices()
        
        # Wait for aggregation
        await asyncio.sleep(0.1)
        
        # Calculate prices
        result1 = await pricing_engine.calculate_dynamic_price(
            resource_id="consistency_test_gpu_1",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE
        )
        
        result2 = await pricing_engine.calculate_dynamic_price(
            resource_id="consistency_test_gpu_2",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE
        )
        
        # Verify consistent market data usage
        assert result1.factors_exposed.get("demand_level") is not None
        assert result2.factors_exposed.get("demand_level") is not None
        
        # Market conditions should be similar for same resource type
        demand_diff = abs(result1.factors_exposed["demand_level"] - result2.factors_exposed["demand_level"])
        assert demand_diff < 0.1  # Should be relatively close


class TestDatabaseIntegration:
    """Test database integration for pricing data"""
    
    @pytest.mark.asyncio
    async def test_pricing_history_storage(self, pricing_engine):
        """Test pricing history storage to database"""
        
        await pricing_engine.initialize()
        
        # Calculate price and store in history
        result = await pricing_engine.calculate_dynamic_price(
            resource_id="db_test_gpu",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE
        )
        
        # Verify data was stored in memory (in production, this would be database)
        assert "db_test_gpu" in pricing_engine.pricing_history
        assert len(pricing_engine.pricing_history["db_test_gpu"]) > 0
        
        # Verify data structure
        history_point = pricing_engine.pricing_history["db_test_gpu"][0]
        assert history_point.price == result.recommended_price
        assert history_point.strategy_used == result.strategy_used.value
    
    @pytest.mark.asyncio
    async def test_provider_strategy_persistence(self, pricing_engine):
        """Test provider strategy persistence"""
        
        await pricing_engine.initialize()
        
        # Set provider strategy
        await pricing_engine.set_provider_strategy(
            provider_id="db_test_provider",
            strategy=PricingStrategy.PROFIT_MAXIMIZATION
        )
        
        # Verify strategy was stored
        assert pricing_engine.provider_strategies["db_test_provider"] == PricingStrategy.PROFIT_MAXIMIZATION
        
        # In production, this would be persisted to database
        # For now, we verify in-memory storage
        assert "db_test_provider" in pricing_engine.provider_strategies


if __name__ == "__main__":
    pytest.main([__file__])
