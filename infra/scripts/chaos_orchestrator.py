#!/usr/bin/env python3
"""
Chaos Testing Orchestrator
Runs multiple chaos test scenarios and aggregates MTTR metrics
"""

import asyncio
import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ChaosOrchestrator:
    """Orchestrates multiple chaos test scenarios"""
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self.results = {
            "orchestration_start": None,
            "orchestration_end": None,
            "scenarios": [],
            "summary": {
                "total_scenarios": 0,
                "successful_scenarios": 0,
                "failed_scenarios": 0,
                "average_mttr": 0,
                "max_mttr": 0,
                "min_mttr": float('inf')
            }
        }
    
    async def run_scenario(self, script: str, args: List[str]) -> Optional[Dict]:
        """Run a single chaos test scenario"""
        scenario_name = Path(script).stem.replace("chaos_test_", "")
        logger.info(f"Running scenario: {scenario_name}")
        
        cmd = ["python3", script] + args
        start_time = time.time()
        
        try:
            # Run the chaos test script
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Scenario {scenario_name} failed with exit code {process.returncode}")
                logger.error(f"Error: {stderr.decode()}")
                return None
            
            # Find the results file
            result_files = list(Path(".").glob(f"chaos_test_{scenario_name}_*.json"))
            if not result_files:
                logger.error(f"No results file found for scenario {scenario_name}")
                return None
            
            # Load the most recent result file
            result_file = max(result_files, key=lambda p: p.stat().st_mtime)
            with open(result_file, 'r') as f:
                results = json.load(f)
            
            # Add execution metadata
            results["execution_time"] = time.time() - start_time
            results["scenario_name"] = scenario_name
            
            logger.info(f"Scenario {scenario_name} completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Failed to run scenario {scenario_name}: {e}")
            return None
    
    def calculate_summary_metrics(self):
        """Calculate summary metrics across all scenarios"""
        mttr_values = []
        
        for scenario in self.results["scenarios"]:
            if scenario.get("mttr"):
                mttr_values.append(scenario["mttr"])
        
        if mttr_values:
            self.results["summary"]["average_mttr"] = sum(mttr_values) / len(mttr_values)
            self.results["summary"]["max_mttr"] = max(mttr_values)
            self.results["summary"]["min_mttr"] = min(mttr_values)
        
        self.results["summary"]["total_scenarios"] = len(self.results["scenarios"])
        self.results["summary"]["successful_scenarios"] = sum(
            1 for s in self.results["scenarios"] if s.get("mttr") is not None
        )
        self.results["summary"]["failed_scenarios"] = (
            self.results["summary"]["total_scenarios"] - 
            self.results["summary"]["successful_scenarios"]
        )
    
    def generate_report(self, output_file: Optional[str] = None):
        """Generate a comprehensive chaos test report"""
        report = {
            "report_generated": datetime.utcnow().isoformat(),
            "namespace": self.namespace,
            "orchestration": self.results,
            "recommendations": []
        }
        
        # Add recommendations based on results
        if self.results["summary"]["average_mttr"] > 120:
            report["recommendations"].append(
                "Average MTTR exceeds 2 minutes. Consider improving recovery automation."
            )
        
        if self.results["summary"]["max_mttr"] > 300:
            report["recommendations"].append(
                "Maximum MTTR exceeds 5 minutes. Review slowest recovery scenario."
            )
        
        if self.results["summary"]["failed_scenarios"] > 0:
            report["recommendations"].append(
                f"{self.results['summary']['failed_scenarios']} scenario(s) failed. Review test configuration."
            )
        
        # Check for specific scenario issues
        for scenario in self.results["scenarios"]:
            if scenario.get("scenario_name") == "coordinator_outage":
                if scenario.get("mttr", 0) > 180:
                    report["recommendations"].append(
                        "Coordinator recovery is slow. Consider reducing pod startup time."
                    )
            
            elif scenario.get("scenario_name") == "network_partition":
                if scenario.get("error_count", 0) > scenario.get("success_count", 0):
                    report["recommendations"].append(
                        "High error rate during network partition. Improve error handling."
                    )
            
            elif scenario.get("scenario_name") == "database_failure":
                if scenario.get("failure_type") == "connection":
                    report["recommendations"].append(
                        "Consider implementing database connection pooling and retry logic."
                    )
        
        # Save report
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Chaos test report saved to: {output_file}")
        
        # Print summary
        self.print_summary()
        
        return report
    
    def print_summary(self):
        """Print a summary of all chaos test results"""
        print("\n" + "="*60)
        print("CHAOS TESTING SUMMARY REPORT")
        print("="*60)
        
        print(f"\nTest Execution: {self.results['orchestration_start']} to {self.results['orchestration_end']}")
        print(f"Namespace: {self.namespace}")
        
        print(f"\nScenario Results:")
        print("-" * 40)
        for scenario in self.results["scenarios"]:
            name = scenario.get("scenario_name", "Unknown")
            mttr = scenario.get("mttr", "N/A")
            if mttr != "N/A":
                mttr = f"{mttr:.2f}s"
            print(f"  {name:20} MTTR: {mttr}")
        
        print(f"\nSummary Metrics:")
        print("-" * 40)
        print(f"  Total Scenarios:     {self.results['summary']['total_scenarios']}")
        print(f"  Successful:          {self.results['summary']['successful_scenarios']}")
        print(f"  Failed:              {self.results['summary']['failed_scenarios']}")
        
        if self.results["summary"]["average_mttr"] > 0:
            print(f"  Average MTTR:        {self.results['summary']['average_mttr']:.2f}s")
            print(f"  Maximum MTTR:        {self.results['summary']['max_mttr']:.2f}s")
            print(f"  Minimum MTTR:        {self.results['summary']['min_mttr']:.2f}s")
        
        # SLO compliance
        print(f"\nSLO Compliance:")
        print("-" * 40)
        slo_target = 120  # 2 minutes
        if self.results["summary"]["average_mttr"] <= slo_target:
            print(f"  ✓ Average MTTR within SLO ({slo_target}s)")
        else:
            print(f"  ✗ Average MTTR exceeds SLO ({slo_target}s)")
        
        print("\n" + "="*60)
    
    async def run_all_scenarios(self, scenarios: List[str], scenario_args: Dict[str, List[str]]):
        """Run all specified chaos test scenarios"""
        logger.info("Starting chaos testing orchestration")
        self.results["orchestration_start"] = datetime.utcnow().isoformat()
        
        for scenario in scenarios:
            args = scenario_args.get(scenario, [])
            # Add namespace to all scenarios
            args.extend(["--namespace", self.namespace])
            
            result = await self.run_scenario(scenario, args)
            if result:
                self.results["scenarios"].append(result)
        
        self.results["orchestration_end"] = datetime.utcnow().isoformat()
        
        # Calculate summary metrics
        self.calculate_summary_metrics()
        
        # Generate report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"chaos_test_report_{timestamp}.json"
        self.generate_report(report_file)
        
        logger.info("Chaos testing orchestration completed")
    
    async def run_continuous_chaos(self, duration_hours: int = 24, interval_minutes: int = 60):
        """Run chaos tests continuously over time"""
        logger.info(f"Starting continuous chaos testing for {duration_hours} hours")
        
        end_time = datetime.now() + timedelta(hours=duration_hours)
        interval_seconds = interval_minutes * 60
        
        all_results = []
        
        while datetime.now() < end_time:
            cycle_start = datetime.now()
            logger.info(f"Starting chaos test cycle at {cycle_start}")
            
            # Run a random scenario
            scenarios = [
                "chaos_test_coordinator.py",
                "chaos_test_network.py",
                "chaos_test_database.py"
            ]
            
            import random
            selected_scenario = random.choice(scenarios)
            
            # Run scenario with reduced duration for continuous testing
            args = ["--namespace", self.namespace]
            if "coordinator" in selected_scenario:
                args.extend(["--outage-duration", "30", "--load-duration", "60"])
            elif "network" in selected_scenario:
                args.extend(["--partition-duration", "30", "--partition-ratio", "0.3"])
            elif "database" in selected_scenario:
                args.extend(["--failure-duration", "30", "--failure-type", "connection"])
            
            result = await self.run_scenario(selected_scenario, args)
            if result:
                result["cycle_time"] = cycle_start.isoformat()
                all_results.append(result)
            
            # Wait for next cycle
            elapsed = (datetime.now() - cycle_start).total_seconds()
            if elapsed < interval_seconds:
                wait_time = interval_seconds - elapsed
                logger.info(f"Waiting {wait_time:.0f}s for next cycle")
                await asyncio.sleep(wait_time)
        
        # Generate continuous testing report
        continuous_report = {
            "continuous_testing": True,
            "duration_hours": duration_hours,
            "interval_minutes": interval_minutes,
            "total_cycles": len(all_results),
            "cycles": all_results
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"continuous_chaos_report_{timestamp}.json"
        with open(report_file, 'w') as f:
            json.dump(continuous_report, f, indent=2)
        
        logger.info(f"Continuous chaos testing completed. Report saved to: {report_file}")


async def main():
    parser = argparse.ArgumentParser(description="Chaos testing orchestrator")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--scenarios", nargs="+", 
                       choices=["coordinator", "network", "database"],
                       default=["coordinator", "network", "database"],
                       help="Scenarios to run")
    parser.add_argument("--continuous", action="store_true", help="Run continuous chaos testing")
    parser.add_argument("--duration", type=int, default=24, help="Duration in hours for continuous testing")
    parser.add_argument("--interval", type=int, default=60, help="Interval in minutes for continuous testing")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without actual chaos")
    
    args = parser.parse_args()
    
    # Verify kubectl is available
    try:
        subprocess.run(["kubectl", "version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("kubectl is not available or not configured")
        sys.exit(1)
    
    orchestrator = ChaosOrchestrator(args.namespace)
    
    if args.dry_run:
        logger.info(f"DRY RUN: Would run scenarios: {', '.join(args.scenarios)}")
        return
    
    if args.continuous:
        await orchestrator.run_continuous_chaos(args.duration, args.interval)
    else:
        # Map scenario names to script files
        scenario_map = {
            "coordinator": "chaos_test_coordinator.py",
            "network": "chaos_test_network.py",
            "database": "chaos_test_database.py"
        }
        
        # Get script files
        scripts = [scenario_map[s] for s in args.scenarios]
        
        # Default arguments for each scenario
        scenario_args = {
            "chaos_test_coordinator.py": ["--outage-duration", "60", "--load-duration", "120"],
            "chaos_test_network.py": ["--partition-duration", "60", "--partition-ratio", "0.5"],
            "chaos_test_database.py": ["--failure-duration", "60", "--failure-type", "connection"]
        }
        
        await orchestrator.run_all_scenarios(scripts, scenario_args)


if __name__ == "__main__":
    asyncio.run(main())
