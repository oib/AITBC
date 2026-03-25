#!/usr/bin/env python3
"""
Comprehensive OpenClaw Agent Marketplace Test Runner
Executes all test suites for Phase 8-10 implementation
"""

import pytest
import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add the tests directory to Python path
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

class OpenClawTestRunner:
    """Comprehensive test runner for OpenClaw Agent Marketplace"""
    
    def __init__(self):
        self.test_suites = {
            "framework": "test_framework.py",
            "multi_region": "test_multi_region_deployment.py", 
            "blockchain": "test_blockchain_integration.py",
            "economics": "test_agent_economics.py",
            "capabilities": "test_advanced_agent_capabilities.py",
            "performance": "test_performance_optimization.py",
            "governance": "test_agent_governance.py"
        }
        self.results = {}
        self.start_time = datetime.now()
        
    def run_test_suite(self, suite_name: str, test_file: str) -> Dict[str, Any]:
        """Run a specific test suite"""
        print(f"\n{'='*60}")
        print(f"Running {suite_name.upper()} Test Suite")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        # Configure pytest arguments
        pytest_args = [
            str(test_dir / test_file),
            "-v",
            "--tb=short",
            "--json-report",
            "--json-report-file=/tmp/test_report.json",
            "-x"  # Stop on first failure for debugging
        ]
        
        # Run pytest and capture results
        exit_code = pytest.main(pytest_args)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Load JSON report if available
        report_file = "/tmp/test_report.json"
        test_results = {}
        
        if os.path.exists(report_file):
            try:
                with open(report_file, 'r') as f:
                    test_results = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load test report: {e}")
        
        suite_result = {
            "suite_name": suite_name,
            "exit_code": exit_code,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "test_results": test_results,
            "success": exit_code == 0
        }
        
        # Print summary
        if exit_code == 0:
            print(f"✅ {suite_name.upper()} tests PASSED ({duration:.2f}s)")
        else:
            print(f"❌ {suite_name.upper()} tests FAILED ({duration:.2f}s)")
            
        if test_results.get("summary"):
            summary = test_results["summary"]
            print(f"   Tests: {summary.get('total', 0)}")
            print(f"   Passed: {summary.get('passed', 0)}")
            print(f"   Failed: {summary.get('failed', 0)}")
            print(f"   Skipped: {summary.get('skipped', 0)}")
            
        return suite_result
        
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all test suites"""
        print(f"\n🚀 Starting OpenClaw Agent Marketplace Test Suite")
        print(f"📅 Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📁 Test directory: {test_dir}")
        
        total_suites = len(self.test_suites)
        passed_suites = 0
        
        for suite_name, test_file in self.test_suites.items():
            result = self.run_test_suite(suite_name, test_file)
            self.results[suite_name] = result
            
            if result["success"]:
                passed_suites += 1
                
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        # Generate final report
        final_report = {
            "test_run_summary": {
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "total_duration": total_duration,
                "total_suites": total_suites,
                "passed_suites": passed_suites,
                "failed_suites": total_suites - passed_suites,
                "success_rate": (passed_suites / total_suites) * 100
            },
            "suite_results": self.results,
            "recommendations": self._generate_recommendations()
        }
        
        # Print final summary
        self._print_final_summary(final_report)
        
        # Save detailed report
        report_file = test_dir / "test_results.json"
        with open(report_file, 'w') as f:
            json.dump(final_report, f, indent=2)
            
        print(f"\n📄 Detailed report saved to: {report_file}")
        
        return final_report
        
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []
        
        failed_suites = [name for name, result in self.results.items() if not result["success"]]
        
        if failed_suites:
            recommendations.append(f"🔧 Fix failing test suites: {', '.join(failed_suites)}")
            
        # Check for specific patterns
        for suite_name, result in self.results.items():
            if not result["success"]:
                if suite_name == "framework":
                    recommendations.append("🏗️  Review test framework setup and configuration")
                elif suite_name == "multi_region":
                    recommendations.append("🌍 Check multi-region deployment configuration")
                elif suite_name == "blockchain":
                    recommendations.append("⛓️  Verify blockchain integration and smart contracts")
                elif suite_name == "economics":
                    recommendations.append("💰 Review agent economics and payment systems")
                elif suite_name == "capabilities":
                    recommendations.append("🤖 Check advanced agent capabilities and AI models")
                elif suite_name == "performance":
                    recommendations.append("⚡ Optimize marketplace performance and resource usage")
                elif suite_name == "governance":
                    recommendations.append("🏛️  Review governance systems and DAO functionality")
                    
        if not failed_suites:
            recommendations.append("🎉 All tests passed! Ready for production deployment")
            recommendations.append("📈 Consider running performance tests under load")
            recommendations.append("🔍 Conduct security audit before production")
            
        return recommendations
        
    def _print_final_summary(self, report: Dict[str, Any]):
        """Print final test summary"""
        summary = report["test_run_summary"]
        
        print(f"\n{'='*80}")
        print(f"🏁 OPENCLAW MARKETPLACE TEST SUITE COMPLETED")
        print(f"{'='*80}")
        print(f"📊 Total Duration: {summary['total_duration']:.2f} seconds")
        print(f"📈 Success Rate: {summary['success_rate']:.1f}%")
        print(f"✅ Passed Suites: {summary['passed_suites']}/{summary['total_suites']}")
        print(f"❌ Failed Suites: {summary['failed_suites']}/{summary['total_suites']}")
        
        if summary['failed_suites'] == 0:
            print(f"\n🎉 ALL TESTS PASSED! 🎉")
            print(f"🚀 OpenClaw Agent Marketplace is ready for deployment!")
        else:
            print(f"\n⚠️  {summary['failed_suites']} test suite(s) failed")
            print(f"🔧 Please review and fix issues before deployment")
            
        print(f"\n📋 RECOMMENDATIONS:")
        for i, rec in enumerate(report["recommendations"], 1):
            print(f"   {i}. {rec}")
            
        print(f"\n{'='*80}")

def main():
    """Main entry point"""
    runner = OpenClawTestRunner()
    
    try:
        results = runner.run_all_tests()
        
        # Exit with appropriate code
        if results["test_run_summary"]["failed_suites"] == 0:
            print(f"\n✅ All tests completed successfully!")
            sys.exit(0)
        else:
            print(f"\n❌ Some tests failed. Check the report for details.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n⏹️  Test run interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
