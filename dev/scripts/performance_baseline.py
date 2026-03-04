#!/usr/bin/env python3
"""
AITBC Performance Baseline Testing

This script establishes performance baselines for the AITBC platform,
including API response times, throughput, resource usage, and user experience metrics.
"""

import asyncio
import json
import logging
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import aiohttp
import psutil
import subprocess
import sys


@dataclass
class PerformanceMetric:
    """Individual performance measurement."""
    timestamp: float
    metric_name: str
    value: float
    unit: str
    context: Dict[str, Any]


@dataclass
class BaselineResult:
    """Performance baseline result."""
    metric_name: str
    baseline_value: float
    unit: str
    samples: int
    min_value: float
    max_value: float
    mean_value: float
    median_value: float
    std_deviation: float
    percentile_95: float
    percentile_99: float
    status: str  # "pass", "warning", "fail"
    threshold: Optional[float]


class PerformanceBaseline:
    """Performance baseline testing system."""
    
    def __init__(self, config_path: str = "config/performance_config.json"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.baselines = self._load_baselines()
        self.current_metrics = []
    
    def _load_config(self, config_path: str) -> Dict:
        """Load performance testing configuration."""
        default_config = {
            "test_duration": 300,  # 5 minutes
            "concurrent_users": 10,
            "ramp_up_time": 60,  # 1 minute
            "endpoints": {
                "health": "https://api.aitbc.dev/health",
                "users": "https://api.aitbc.dev/api/v1/users",
                "transactions": "https://api.aitbc.dev/api/v1/transactions",
                "blockchain": "https://api.aitbc.dev/api/v1/blockchain/status",
                "marketplace": "https://api.aitbc.dev/api/v1/marketplace/listings"
            },
            "thresholds": {
                "response_time_p95": 2000,  # ms
                "response_time_p99": 5000,  # ms
                "error_rate": 1.0,  # %
                "throughput_min": 100,  # requests/second
                "cpu_max": 80,  # %
                "memory_max": 85,  # %
                "disk_io_max": 100  # MB/s
            },
            "scenarios": {
                "light_load": {"users": 5, "duration": 60},
                "medium_load": {"users": 20, "duration": 120},
                "heavy_load": {"users": 50, "duration": 180},
                "stress_test": {"users": 100, "duration": 300}
            }
        }
        
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        
        return default_config
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for performance testing."""
        logger = logging.getLogger("performance_baseline")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _load_baselines(self) -> Dict:
        """Load existing baselines."""
        baseline_file = Path("data/performance_baselines.json")
        if baseline_file.exists():
            with open(baseline_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_baselines(self) -> None:
        """Save baselines to file."""
        baseline_file = Path("data/performance_baselines.json")
        baseline_file.parent.mkdir(exist_ok=True)
        with open(baseline_file, 'w') as f:
            json.dump(self.baselines, f, indent=2)
    
    async def measure_api_response_time(self, endpoint: str, method: str = "GET", 
                                      payload: Dict = None) -> float:
        """Measure API response time."""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == "GET":
                    async with session.get(endpoint) as response:
                        await response.text()
                elif method.upper() == "POST":
                    async with session.post(endpoint, json=payload) as response:
                        await response.text()
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                end_time = time.time()
                return (end_time - start_time) * 1000  # Convert to ms
                
        except Exception as e:
            self.logger.error(f"Error measuring {endpoint}: {e}")
            return -1  # Indicate error
    
    async def run_load_test(self, scenario: str) -> Dict[str, Any]:
        """Run load test scenario."""
        scenario_config = self.config["scenarios"][scenario]
        users = scenario_config["users"]
        duration = scenario_config["duration"]
        
        self.logger.info(f"Running {scenario} load test: {users} users for {duration}s")
        
        results = {
            "scenario": scenario,
            "users": users,
            "duration": duration,
            "start_time": time.time(),
            "metrics": {},
            "system_metrics": []
        }
        
        # Start system monitoring
        monitoring_task = asyncio.create_task(self._monitor_system_resources(results))
        
        # Run concurrent requests
        tasks = []
        for i in range(users):
            task = asyncio.create_task(self._simulate_user(duration))
            tasks.append(task)
        
        # Wait for all tasks to complete
        user_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Stop monitoring
        monitoring_task.cancel()
        
        # Process results
        all_response_times = []
        error_count = 0
        total_requests = 0
        
        for user_result in user_results:
            if isinstance(user_result, Exception):
                error_count += 1
                continue
            
            for metric in user_result:
                if metric.metric_name == "response_time" and metric.value > 0:
                    all_response_times.append(metric.value)
                elif metric.metric_name == "error":
                    error_count += 1
                total_requests += 1
        
        # Calculate statistics
        if all_response_times:
            results["metrics"]["response_time"] = {
                "samples": len(all_response_times),
                "min": min(all_response_times),
                "max": max(all_response_times),
                "mean": statistics.mean(all_response_times),
                "median": statistics.median(all_response_times),
                "std_dev": statistics.stdev(all_response_times) if len(all_response_times) > 1 else 0,
                "p95": self._percentile(all_response_times, 95),
                "p99": self._percentile(all_response_times, 99)
            }
        
        results["metrics"]["error_rate"] = (error_count / total_requests * 100) if total_requests > 0 else 0
        results["metrics"]["throughput"] = total_requests / duration
        results["end_time"] = time.time()
        
        return results
    
    async def _simulate_user(self, duration: int) -> List[PerformanceMetric]:
        """Simulate a single user's activity."""
        metrics = []
        end_time = time.time() + duration
        
        endpoints = list(self.config["endpoints"].keys())
        
        while time.time() < end_time:
            # Random endpoint selection
            endpoint_name = endpoints[hash(str(time.time())) % len(endpoints)]
            endpoint_url = self.config["endpoints"][endpoint_name]
            
            # Measure response time
            response_time = await self.measure_api_response_time(endpoint_url)
            
            if response_time > 0:
                metrics.append(PerformanceMetric(
                    timestamp=time.time(),
                    metric_name="response_time",
                    value=response_time,
                    unit="ms",
                    context={"endpoint": endpoint_name}
                ))
            else:
                metrics.append(PerformanceMetric(
                    timestamp=time.time(),
                    metric_name="error",
                    value=1,
                    unit="count",
                    context={"endpoint": endpoint_name}
                ))
            
            # Random think time (1-5 seconds)
            await asyncio.sleep(1 + (hash(str(time.time())) % 5))
        
        return metrics
    
    async def _monitor_system_resources(self, results: Dict) -> None:
        """Monitor system resources during test."""
        try:
            while True:
                # Collect system metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk_io = psutil.disk_io_counters()
                
                system_metric = {
                    "timestamp": time.time(),
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_read_bytes": disk_io.read_bytes,
                    "disk_write_bytes": disk_io.write_bytes
                }
                
                results["system_metrics"].append(system_metric)
                
                await asyncio.sleep(5)  # Sample every 5 seconds
                
        except asyncio.CancelledError:
            self.logger.info("System monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in system monitoring: {e}")
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0
        
        sorted_values = sorted(values)
        index = (percentile / 100) * (len(sorted_values) - 1)
        
        if index.is_integer():
            return sorted_values[int(index)]
        else:
            lower = sorted_values[int(index)]
            upper = sorted_values[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    async def establish_baseline(self, scenario: str) -> BaselineResult:
        """Establish performance baseline for a scenario."""
        self.logger.info(f"Establishing baseline for {scenario}")
        
        # Run load test
        test_results = await self.run_load_test(scenario)
        
        # Extract key metrics
        response_time_data = test_results["metrics"].get("response_time", {})
        error_rate = test_results["metrics"].get("error_rate", 0)
        throughput = test_results["metrics"].get("throughput", 0)
        
        # Create baseline result for response time
        if response_time_data:
            baseline = BaselineResult(
                metric_name=f"{scenario}_response_time_p95",
                baseline_value=response_time_data["p95"],
                unit="ms",
                samples=response_time_data["samples"],
                min_value=response_time_data["min"],
                max_value=response_time_data["max"],
                mean_value=response_time_data["mean"],
                median_value=response_time_data["median"],
                std_deviation=response_time_data["std_dev"],
                percentile_95=response_time_data["p95"],
                percentile_99=response_time_data["p99"],
                status="pass",
                threshold=self.config["thresholds"]["response_time_p95"]
            )
            
            # Check against threshold
            if baseline.percentile_95 > baseline.threshold:
                baseline.status = "fail"
            elif baseline.percentile_95 > baseline.threshold * 0.8:
                baseline.status = "warning"
            
            # Store baseline
            self.baselines[f"{scenario}_response_time_p95"] = asdict(baseline)
            self._save_baselines()
            
            return baseline
        
        return None
    
    async def compare_with_baseline(self, scenario: str) -> Dict[str, Any]:
        """Compare current performance with established baseline."""
        self.logger.info(f"Comparing {scenario} with baseline")
        
        # Run current test
        current_results = await self.run_load_test(scenario)
        
        # Get baseline
        baseline_key = f"{scenario}_response_time_p95"
        baseline_data = self.baselines.get(baseline_key)
        
        if not baseline_data:
            return {"error": "No baseline found for scenario"}
        
        comparison = {
            "scenario": scenario,
            "baseline": baseline_data,
            "current": current_results["metrics"],
            "comparison": {},
            "status": "unknown"
        }
        
        # Compare response times
        current_p95 = current_results["metrics"].get("response_time", {}).get("p95", 0)
        baseline_p95 = baseline_data["baseline_value"]
        
        if current_p95 > 0:
            percent_change = ((current_p95 - baseline_p95) / baseline_p95) * 100
            comparison["comparison"]["response_time_p95"] = {
                "baseline": baseline_p95,
                "current": current_p95,
                "percent_change": percent_change,
                "status": "pass" if percent_change < 10 else "warning" if percent_change < 25 else "fail"
            }
        
        # Compare error rates
        current_error_rate = current_results["metrics"].get("error_rate", 0)
        baseline_error_rate = baseline_data.get("error_rate", 0)
        
        error_change = current_error_rate - baseline_error_rate
        comparison["comparison"]["error_rate"] = {
            "baseline": baseline_error_rate,
            "current": current_error_rate,
            "change": error_change,
            "status": "pass" if error_change < 0.5 else "warning" if error_change < 2.0 else "fail"
        }
        
        # Compare throughput
        current_throughput = current_results["metrics"].get("throughput", 0)
        baseline_throughput = baseline_data.get("throughput", 0)
        
        if baseline_throughput > 0:
            throughput_change = ((current_throughput - baseline_throughput) / baseline_throughput) * 100
            comparison["comparison"]["throughput"] = {
                "baseline": baseline_throughput,
                "current": current_throughput,
                "percent_change": throughput_change,
                "status": "pass" if throughput_change > -10 else "warning" if throughput_change > -25 else "fail"
            }
        
        # Overall status
        statuses = [cmp.get("status") for cmp in comparison["comparison"].values()]
        if "fail" in statuses:
            comparison["status"] = "fail"
        elif "warning" in statuses:
            comparison["status"] = "warning"
        else:
            comparison["status"] = "pass"
        
        return comparison
    
    async def run_all_scenarios(self) -> Dict[str, Any]:
        """Run all performance test scenarios."""
        results = {}
        
        for scenario in self.config["scenarios"].keys():
            try:
                self.logger.info(f"Running scenario: {scenario}")
                
                # Establish baseline if not exists
                if f"{scenario}_response_time_p95" not in self.baselines:
                    baseline = await self.establish_baseline(scenario)
                    results[scenario] = {"baseline": asdict(baseline)}
                else:
                    # Compare with existing baseline
                    comparison = await self.compare_with_baseline(scenario)
                    results[scenario] = comparison
                
            except Exception as e:
                self.logger.error(f"Error running scenario {scenario}: {e}")
                results[scenario] = {"error": str(e)}
        
        return results
    
    async def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        self.logger.info("Generating performance report")
        
        # Run all scenarios
        scenario_results = await self.run_all_scenarios()
        
        # Calculate overall metrics
        total_scenarios = len(scenario_results)
        passed_scenarios = len([r for r in scenario_results.values() if r.get("status") == "pass"])
        warning_scenarios = len([r for r in scenario_results.values() if r.get("status") == "warning"])
        failed_scenarios = len([r for r in scenario_results.values() if r.get("status") == "fail"])
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_scenarios": total_scenarios,
                "passed": passed_scenarios,
                "warnings": warning_scenarios,
                "failed": failed_scenarios,
                "success_rate": (passed_scenarios / total_scenarios * 100) if total_scenarios > 0 else 0,
                "overall_status": "pass" if failed_scenarios == 0 else "warning" if failed_scenarios == 0 else "fail"
            },
            "scenarios": scenario_results,
            "baselines": self.baselines,
            "thresholds": self.config["thresholds"],
            "recommendations": self._generate_recommendations(scenario_results)
        }
        
        # Save report
        report_file = Path("data/performance_report.json")
        report_file.parent.mkdir(exist_ok=True)
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report
    
    def _generate_recommendations(self, scenario_results: Dict) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []
        
        for scenario, result in scenario_results.items():
            if result.get("status") == "fail":
                recommendations.append(f"URGENT: {scenario} scenario failed performance tests")
            elif result.get("status") == "warning":
                recommendations.append(f"Review {scenario} scenario performance degradation")
        
        # Check for common issues
        high_response_times = []
        high_error_rates = []
        
        for scenario, result in scenario_results.items():
            if "comparison" in result:
                comp = result["comparison"]
                if comp.get("response_time_p95", {}).get("status") == "fail":
                    high_response_times.append(scenario)
                if comp.get("error_rate", {}).get("status") == "fail":
                    high_error_rates.append(scenario)
        
        if high_response_times:
            recommendations.append(f"High response times detected in: {', '.join(high_response_times)}")
        
        if high_error_rates:
            recommendations.append(f"High error rates detected in: {', '.join(high_error_rates)}")
        
        if not recommendations:
            recommendations.append("All performance tests passed. System is performing within expected parameters.")
        
        return recommendations


# CLI interface
async def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC Performance Baseline Testing")
    parser.add_argument("--scenario", help="Run specific scenario")
    parser.add_argument("--baseline", help="Establish baseline for scenario")
    parser.add_argument("--compare", help="Compare scenario with baseline")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--report", action="store_true", help="Generate performance report")
    
    args = parser.parse_args()
    
    baseline = PerformanceBaseline()
    
    if args.scenario:
        if args.baseline:
            result = await baseline.establish_baseline(args.scenario)
            print(f"Baseline established: {result}")
        elif args.compare:
            comparison = await baseline.compare_with_baseline(args.scenario)
            print(json.dumps(comparison, indent=2))
        else:
            result = await baseline.run_load_test(args.scenario)
            print(json.dumps(result, indent=2, default=str))
    
    elif args.all:
        results = await baseline.run_all_scenarios()
        print(json.dumps(results, indent=2, default=str))
    
    elif args.report:
        report = await baseline.generate_performance_report()
        print(json.dumps(report, indent=2))
    
    else:
        print("Use --help to see available options")


if __name__ == "__main__":
    asyncio.run(main())
