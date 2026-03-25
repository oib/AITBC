"""
Performance Tests for Dynamic Pricing System
Tests system performance under load and stress conditions
"""

import pytest
import asyncio
import time
import psutil
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
import statistics

from app.services.dynamic_pricing_engine import DynamicPricingEngine, PricingStrategy, ResourceType
from app.services.market_data_collector import MarketDataCollector


class TestPricingPerformance:
    """Performance tests for the dynamic pricing system"""
    
    @pytest.fixture
    def pricing_engine(self):
        """Create pricing engine optimized for performance testing"""
        config = {
            "min_price": 0.001,
            "max_price": 1000.0,
            "update_interval": 60,
            "forecast_horizon": 24,
            "max_volatility_threshold": 0.3,
            "circuit_breaker_threshold": 0.5
        }
        engine = DynamicPricingEngine(config)
        return engine
    
    @pytest.fixture
    def market_collector(self):
        """Create market data collector for performance testing"""
        config = {
            "websocket_port": 8767
        }
        collector = MarketDataCollector(config)
        return collector
    
    @pytest.mark.asyncio
    async def test_single_pricing_calculation_performance(self, pricing_engine):
        """Test performance of individual pricing calculations"""
        
        await pricing_engine.initialize()
        
        # Measure single calculation time
        start_time = time.time()
        
        result = await pricing_engine.calculate_dynamic_price(
            resource_id="perf_test_gpu",
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE
        )
        
        end_time = time.time()
        calculation_time = end_time - start_time
        
        # Performance assertions
        assert calculation_time < 0.1  # Should complete within 100ms
        assert result.recommended_price > 0
        assert result.confidence_score > 0
        
        print(f"Single calculation time: {calculation_time:.4f}s")
    
    @pytest.mark.asyncio
    async def test_concurrent_pricing_calculations(self, pricing_engine):
        """Test performance of concurrent pricing calculations"""
        
        await pricing_engine.initialize()
        
        num_concurrent = 100
        num_iterations = 10
        
        all_times = []
        
        for iteration in range(num_iterations):
            # Create concurrent tasks
            tasks = []
            start_time = time.time()
            
            for i in range(num_concurrent):
                task = pricing_engine.calculate_dynamic_price(
                    resource_id=f"concurrent_perf_gpu_{iteration}_{i}",
                    resource_type=ResourceType.GPU,
                    base_price=0.05,
                    strategy=PricingStrategy.MARKET_BALANCE
                )
                tasks.append(task)
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks)
            
            end_time = time.time()
            iteration_time = end_time - start_time
            all_times.append(iteration_time)
            
            # Verify all calculations completed successfully
            assert len(results) == num_concurrent
            for result in results:
                assert result.recommended_price > 0
                assert result.confidence_score > 0
            
            print(f"Iteration {iteration + 1}: {num_concurrent} calculations in {iteration_time:.4f}s")
        
        # Performance analysis
        avg_time = statistics.mean(all_times)
        min_time = min(all_times)
        max_time = max(all_times)
        std_dev = statistics.stdev(all_times)
        
        print(f"Concurrent performance stats:")
        print(f"  Average time: {avg_time:.4f}s")
        print(f"  Min time: {min_time:.4f}s")
        print(f"  Max time: {max_time:.4f}s")
        print(f"  Std deviation: {std_dev:.4f}s")
        
        # Performance assertions
        assert avg_time < 2.0  # Should complete 100 calculations within 2 seconds
        assert std_dev < 0.5  # Low variance in performance
    
    @pytest.mark.asyncio
    async def test_high_volume_pricing_calculations(self, pricing_engine):
        """Test performance under high volume load"""
        
        await pricing_engine.initialize()
        
        num_calculations = 1000
        batch_size = 50
        
        start_time = time.time()
        
        # Process in batches to avoid overwhelming the system
        for batch_start in range(0, num_calculations, batch_size):
            batch_end = min(batch_start + batch_size, num_calculations)
            
            tasks = []
            for i in range(batch_start, batch_end):
                task = pricing_engine.calculate_dynamic_price(
                    resource_id=f"high_volume_gpu_{i}",
                    resource_type=ResourceType.GPU,
                    base_price=0.05,
                    strategy=PricingStrategy.MARKET_BALANCE
                )
                tasks.append(task)
            
            await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        calculations_per_second = num_calculations / total_time
        
        print(f"High volume test:")
        print(f"  {num_calculations} calculations in {total_time:.2f}s")
        print(f"  {calculations_per_second:.2f} calculations/second")
        
        # Performance assertions
        assert calculations_per_second > 50  # Should handle at least 50 calculations per second
        assert total_time < 30  # Should complete within 30 seconds
    
    @pytest.mark.asyncio
    async def test_forecast_generation_performance(self, pricing_engine):
        """Test performance of price forecast generation"""
        
        await pricing_engine.initialize()
        
        # Add historical data for forecasting
        base_time = datetime.utcnow()
        for i in range(100):  # 100 data points
            pricing_engine.pricing_history["forecast_perf_gpu"] = pricing_engine.pricing_history.get("forecast_perf_gpu", [])
            pricing_engine.pricing_history["forecast_perf_gpu"].append(
                Mock(
                    price=0.05 + (i * 0.0001),
                    demand_level=0.6 + (i % 10) * 0.02,
                    supply_level=0.7 - (i % 8) * 0.01,
                    confidence=0.8,
                    strategy_used="market_balance",
                    timestamp=base_time - timedelta(hours=100-i)
                )
            )
        
        # Test forecast generation performance
        forecast_horizons = [24, 48, 72]
        forecast_times = []
        
        for horizon in forecast_horizons:
            start_time = time.time()
            
            forecast = await pricing_engine.get_price_forecast("forecast_perf_gpu", horizon)
            
            end_time = time.time()
            forecast_time = end_time - start_time
            forecast_times.append(forecast_time)
            
            assert len(forecast) == horizon
            print(f"Forecast {horizon}h: {forecast_time:.4f}s ({len(forecast)} points)")
        
        # Performance assertions
        avg_forecast_time = statistics.mean(forecast_times)
        assert avg_forecast_time < 0.5  # Forecasts should complete within 500ms
    
    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, pricing_engine):
        """Test memory usage during high load"""
        
        await pricing_engine.initialize()
        
        # Measure initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate high load
        num_calculations = 500
        
        for i in range(num_calculations):
            await pricing_engine.calculate_dynamic_price(
                resource_id=f"memory_test_gpu_{i}",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE
            )
        
        # Measure memory usage after load
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"Memory usage test:")
        print(f"  Initial memory: {initial_memory:.2f} MB")
        print(f"  Final memory: {final_memory:.2f} MB")
        print(f"  Memory increase: {memory_increase:.2f} MB")
        print(f"  Memory per calculation: {memory_increase/num_calculations:.4f} MB")
        
        # Memory assertions
        assert memory_increase < 100  # Should not increase by more than 100MB
        assert memory_increase / num_calculations < 0.5  # Less than 0.5MB per calculation
    
    @pytest.mark.asyncio
    async def test_market_data_collection_performance(self, market_collector):
        """Test performance of market data collection"""
        
        await market_collector.initialize()
        
        # Measure data collection performance
        collection_times = {}
        
        for source in market_collector.collection_intervals.keys():
            start_time = time.time()
            
            await market_collector._collect_from_source(source)
            
            end_time = time.time()
            collection_time = end_time - start_time
            collection_times[source.value] = collection_time
            
            print(f"Data collection {source.value}: {collection_time:.4f}s")
        
        # Performance assertions
        for source, collection_time in collection_times.items():
            assert collection_time < 1.0  # Each collection should complete within 1 second
        
        total_collection_time = sum(collection_times.values())
        assert total_collection_time < 5.0  # All collections should complete within 5 seconds
    
    @pytest.mark.asyncio
    async def test_strategy_switching_performance(self, pricing_engine):
        """Test performance of strategy switching"""
        
        await pricing_engine.initialize()
        
        strategies = [
            PricingStrategy.AGGRESSIVE_GROWTH,
            PricingStrategy.PROFIT_MAXIMIZATION,
            PricingStrategy.MARKET_BALANCE,
            PricingStrategy.COMPETITIVE_RESPONSE,
            PricingStrategy.DEMAND_ELASTICITY
        ]
        
        switch_times = []
        
        for strategy in strategies:
            start_time = time.time()
            
            await pricing_engine.set_provider_strategy(
                provider_id="switch_test_provider",
                strategy=strategy
            )
            
            # Calculate price with new strategy
            await pricing_engine.calculate_dynamic_price(
                resource_id="switch_test_gpu",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=strategy
            )
            
            end_time = time.time()
            switch_time = end_time - start_time
            switch_times.append(switch_time)
            
            print(f"Strategy switch to {strategy.value}: {switch_time:.4f}s")
        
        # Performance assertions
        avg_switch_time = statistics.mean(switch_times)
        assert avg_switch_time < 0.05  # Strategy switches should be very fast
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_performance(self, pricing_engine):
        """Test circuit breaker performance under stress"""
        
        await pricing_engine.initialize()
        
        # Add pricing history
        base_time = datetime.utcnow()
        for i in range(10):
            pricing_engine.pricing_history["circuit_perf_gpu"] = pricing_engine.pricing_history.get("circuit_perf_gpu", [])
            pricing_engine.pricing_history["circuit_perf_gpu"].append(
                Mock(
                    price=0.05,
                    timestamp=base_time - timedelta(minutes=10-i),
                    demand_level=0.5,
                    supply_level=0.5,
                    confidence=0.8,
                    strategy_used="market_balance"
                )
            )
        
        # Test circuit breaker activation performance
        start_time = time.time()
        
        # Simulate high volatility conditions
        with patch.object(pricing_engine, '_get_market_conditions') as mock_conditions:
            mock_conditions.return_value = Mock(
                demand_level=0.9,
                supply_level=0.3,
                price_volatility=0.8,  # High volatility
                utilization_rate=0.95
            )
            
            result = await pricing_engine.calculate_dynamic_price(
                resource_id="circuit_perf_gpu",
                resource_type=ResourceType.GPU,
                base_price=0.05,
                strategy=PricingStrategy.MARKET_BALANCE
            )
        
        end_time = time.time()
        circuit_time = end_time - start_time
        
        print(f"Circuit breaker activation: {circuit_time:.4f}s")
        
        # Verify circuit breaker was activated
        assert "circuit_perf_gpu" in pricing_engine.circuit_breakers
        assert pricing_engine.circuit_breakers["circuit_perf_gpu"] is True
        
        # Performance assertions
        assert circuit_time < 0.1  # Circuit breaker should be very fast
    
    @pytest.mark.asyncio
    async def test_price_history_scaling(self, pricing_engine):
        """Test performance with large price history"""
        
        await pricing_engine.initialize()
        
        # Build large price history
        num_history_points = 10000
        resource_id = "scaling_test_gpu"
        
        print(f"Building {num_history_points} history points...")
        build_start = time.time()
        
        base_time = datetime.utcnow()
        for i in range(num_history_points):
            pricing_engine.pricing_history[resource_id] = pricing_engine.pricing_history.get(resource_id, [])
            pricing_engine.pricing_history[resource_id].append(
                Mock(
                    price=0.05 + (i * 0.00001),
                    demand_level=0.6 + (i % 10) * 0.02,
                    supply_level=0.7 - (i % 8) * 0.01,
                    confidence=0.8,
                    strategy_used="market_balance",
                    timestamp=base_time - timedelta(minutes=num_history_points-i)
                )
            )
        
        build_end = time.time()
        build_time = build_end - build_start
        
        print(f"History build time: {build_time:.4f}s")
        print(f"History size: {len(pricing_engine.pricing_history[resource_id])} points")
        
        # Test calculation performance with large history
        calc_start = time.time()
        
        result = await pricing_engine.calculate_dynamic_price(
            resource_id=resource_id,
            resource_type=ResourceType.GPU,
            base_price=0.05,
            strategy=PricingStrategy.MARKET_BALANCE
        )
        
        calc_end = time.time()
        calc_time = calc_end - calc_start
        
        print(f"Calculation with large history: {calc_time:.4f}s")
        
        # Performance assertions
        assert build_time < 5.0  # History building should be fast
        assert calc_time < 0.5  # Calculation should still be fast even with large history
        assert len(pricing_engine.pricing_history[resource_id]) <= 1000  # Should enforce limit
    
    def test_thread_safety(self, pricing_engine):
        """Test thread safety of pricing calculations"""
        
        # This test uses threading to simulate concurrent access
        def calculate_price_thread(thread_id, num_calculations, results):
            """Thread function for pricing calculations"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                for i in range(num_calculations):
                    result = loop.run_until_complete(
                        pricing_engine.calculate_dynamic_price(
                            resource_id=f"thread_test_gpu_{thread_id}_{i}",
                            resource_type=ResourceType.GPU,
                            base_price=0.05,
                            strategy=PricingStrategy.MARKET_BALANCE
                        )
                    )
                    results.append((thread_id, i, result.recommended_price))
            finally:
                loop.close()
        
        # Run multiple threads
        num_threads = 5
        calculations_per_thread = 20
        results = []
        threads = []
        
        start_time = time.time()
        
        # Create and start threads
        for thread_id in range(num_threads):
            thread = threading.Thread(
                target=calculate_price_thread,
                args=(thread_id, calculations_per_thread, results)
            )
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"Thread safety test:")
        print(f"  {num_threads} threads, {calculations_per_thread} calculations each")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Results: {len(results)} calculations completed")
        
        # Verify all calculations completed
        assert len(results) == num_threads * calculations_per_thread
        
        # Verify no corruption in results
        for thread_id, calc_id, price in results:
            assert price > 0
            assert price < pricing_engine.max_price


class TestLoadTesting:
    """Load testing scenarios for the pricing system"""
    
    @pytest.mark.asyncio
    async def test_sustained_load(self, pricing_engine):
        """Test system performance under sustained load"""
        
        await pricing_engine.initialize()
        
        # Sustained load parameters
        duration_seconds = 30
        calculations_per_second = 50
        total_calculations = duration_seconds * calculations_per_second
        
        results = []
        errors = []
        
        async def sustained_load_worker():
            """Worker for sustained load testing"""
            for i in range(total_calculations):
                try:
                    start_time = time.time()
                    
                    result = await pricing_engine.calculate_dynamic_price(
                        resource_id=f"sustained_gpu_{i}",
                        resource_type=ResourceType.GPU,
                        base_price=0.05,
                        strategy=PricingStrategy.MARKET_BALANCE
                    )
                    
                    end_time = time.time()
                    calculation_time = end_time - start_time
                    
                    results.append({
                        "calculation_id": i,
                        "time": calculation_time,
                        "price": result.recommended_price,
                        "confidence": result.confidence_score
                    })
                    
                    # Rate limiting
                    await asyncio.sleep(1.0 / calculations_per_second)
                    
                except Exception as e:
                    errors.append({"calculation_id": i, "error": str(e)})
        
        # Run sustained load test
        start_time = time.time()
        await sustained_load_worker()
        end_time = time.time()
        
        actual_duration = end_time - start_time
        
        # Analyze results
        calculation_times = [r["time"] for r in results]
        avg_time = statistics.mean(calculation_times)
        p95_time = sorted(calculation_times)[int(len(calculation_times) * 0.95)]
        p99_time = sorted(calculation_times)[int(len(calculation_times) * 0.99)]
        
        print(f"Sustained load test results:")
        print(f"  Duration: {actual_duration:.2f}s (target: {duration_seconds}s)")
        print(f"  Calculations: {len(results)} (target: {total_calculations})")
        print(f"  Errors: {len(errors)}")
        print(f"  Average time: {avg_time:.4f}s")
        print(f"  95th percentile: {p95_time:.4f}s")
        print(f"  99th percentile: {p99_time:.4f}s")
        
        # Performance assertions
        assert len(errors) == 0  # No errors should occur
        assert len(results) >= total_calculations * 0.95  # At least 95% of calculations completed
        assert avg_time < 0.1  # Average calculation time under 100ms
        assert p95_time < 0.2  # 95th percentile under 200ms
    
    @pytest.mark.asyncio
    async def test_burst_load(self, pricing_engine):
        """Test system performance under burst load"""
        
        await pricing_engine.initialize()
        
        # Burst load parameters
        num_bursts = 5
        calculations_per_burst = 100
        burst_interval = 2  # seconds between bursts
        
        burst_results = []
        
        for burst_id in range(num_bursts):
            print(f"Starting burst {burst_id + 1}/{num_bursts}")
            
            start_time = time.time()
            
            # Create burst of calculations
            tasks = []
            for i in range(calculations_per_burst):
                task = pricing_engine.calculate_dynamic_price(
                    resource_id=f"burst_gpu_{burst_id}_{i}",
                    resource_type=ResourceType.GPU,
                    base_price=0.05,
                    strategy=PricingStrategy.MARKET_BALANCE
                )
                tasks.append(task)
            
            # Execute burst
            results = await asyncio.gather(*tasks)
            
            end_time = time.time()
            burst_time = end_time - start_time
            
            burst_results.append({
                "burst_id": burst_id,
                "time": burst_time,
                "calculations": len(results),
                "throughput": len(results) / burst_time
            })
            
            print(f"  Burst {burst_id + 1}: {len(results)} calculations in {burst_time:.4f}s")
            print(f"  Throughput: {len(results) / burst_time:.2f} calc/s")
            
            # Wait between bursts
            if burst_id < num_bursts - 1:
                await asyncio.sleep(burst_interval)
        
        # Analyze burst performance
        throughputs = [b["throughput"] for b in burst_results]
        avg_throughput = statistics.mean(throughputs)
        min_throughput = min(throughputs)
        max_throughput = max(throughputs)
        
        print(f"Burst load test results:")
        print(f"  Average throughput: {avg_throughput:.2f} calc/s")
        print(f"  Min throughput: {min_throughput:.2f} calc/s")
        print(f"  Max throughput: {max_throughput:.2f} calc/s")
        
        # Performance assertions
        assert avg_throughput > 100  # Should handle at least 100 calculations per second
        assert min_throughput > 50   # Even slowest burst should be reasonable
    
    @pytest.mark.asyncio
    async def test_stress_testing(self, pricing_engine):
        """Stress test with extreme load conditions"""
        
        await pricing_engine.initialize()
        
        # Stress test parameters
        stress_duration = 60  # seconds
        max_concurrent = 200
        calculation_interval = 0.01  # very aggressive
        
        results = []
        errors = []
        start_time = time.time()
        
        async def stress_worker():
            """Worker for stress testing"""
            calculation_id = 0
            
            while time.time() - start_time < stress_duration:
                try:
                    # Create batch of concurrent calculations
                    batch_size = min(max_concurrent, 50)
                    tasks = []
                    
                    for i in range(batch_size):
                        task = pricing_engine.calculate_dynamic_price(
                            resource_id=f"stress_gpu_{calculation_id}_{i}",
                            resource_type=ResourceType.GPU,
                            base_price=0.05,
                            strategy=PricingStrategy.MARKET_BALANCE
                        )
                        tasks.append(task)
                    
                    # Execute batch
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Process results
                    for result in batch_results:
                        if isinstance(result, Exception):
                            errors.append(str(result))
                        else:
                            results.append(result)
                    
                    calculation_id += batch_size
                    
                    # Very short interval
                    await asyncio.sleep(calculation_interval)
                    
                except Exception as e:
                    errors.append(str(e))
                    break
        
        # Run stress test
        await stress_worker()
        
        end_time = time.time()
        actual_duration = end_time - start_time
        
        # Analyze stress test results
        total_calculations = len(results)
        error_rate = len(errors) / (len(results) + len(errors)) if (len(results) + len(errors)) > 0 else 0
        throughput = total_calculations / actual_duration
        
        print(f"Stress test results:")
        print(f"  Duration: {actual_duration:.2f}s")
        print(f"  Calculations: {total_calculations}")
        print(f"  Errors: {len(errors)}")
        print(f"  Error rate: {error_rate:.2%}")
        print(f"  Throughput: {throughput:.2f} calc/s")
        
        # Stress test assertions (more lenient than normal tests)
        assert error_rate < 0.05  # Error rate should be under 5%
        assert throughput > 20   # Should maintain reasonable throughput even under stress
        assert actual_duration >= stress_duration * 0.9  # Should run for most of the duration


if __name__ == "__main__":
    pytest.main([__file__])
