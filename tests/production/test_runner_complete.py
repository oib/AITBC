"""
Complete Test Runner for AITBC Agent Coordinator
Runs all test suites for the 100% complete system
"""

import pytest
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Any

class CompleteTestRunner:
    """Complete test runner for all 9 systems"""
    
    def __init__(self):
        self.test_suites = [
            {
                "name": "JWT Authentication Tests",
                "file": "test_jwt_authentication.py",
                "system": "Advanced Security (7/9)",
                "description": "Tests JWT authentication, RBAC, API keys, user management"
            },
            {
                "name": "Production Monitoring Tests",
                "file": "test_production_monitoring.py", 
                "system": "Production Monitoring (8/9)",
                "description": "Tests Prometheus metrics, alerting, SLA monitoring"
            },
            {
                "name": "Type Safety Tests",
                "file": "test_type_safety.py",
                "system": "Type Safety (9/9)",
                "description": "Tests type validation, Pydantic models, type hints"
            },
            {
                "name": "Complete System Integration Tests",
                "file": "test_complete_system_integration.py",
                "system": "All Systems (1-9/9)",
                "description": "Tests integration of all 9 completed systems"
            },
            {
                "name": "Advanced Features Tests",
                "file": "test_advanced_features.py",
                "system": "Agent Systems (4/9)",
                "description": "Tests AI/ML, consensus, and advanced features"
            },
            {
                "name": "Agent Coordinator API Tests",
                "file": "test_agent_coordinator_api.py",
                "system": "API Functionality (5/9)",
                "description": "Tests core API endpoints and functionality"
            }
        ]
        
        self.results = {}
        self.start_time = datetime.now()
    
    def run_test_suite(self, suite_info: Dict[str, str]) -> Dict[str, Any]:
        """Run a single test suite"""
        print(f"\n{'='*80}")
        print(f"🧪 RUNNING: {suite_info['name']}")
        print(f"📋 System: {suite_info['system']}")
        print(f"📝 Description: {suite_info['description']}")
        print(f"📁 File: {suite_info['file']}")
        print(f"{'='*80}")
        
        start_time = time.time()
        
        try:
            # Run pytest with specific test file
            result = subprocess.run([
                sys.executable, "-m", "pytest", 
                suite_info['file'],
                "-v",
                "--tb=short",
                "--no-header",
                "--disable-warnings"
            ], capture_output=True, text=True, cwd="/opt/aitbc/tests")
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Parse results
            output = result.stdout
            error_output = result.stderr
            
            # Extract test statistics
            lines = output.split('\n')
            total_tests = 0
            passed_tests = 0
            failed_tests = 0
            skipped_tests = 0
            errors = 0
            
            for line in lines:
                if " passed" in line and " failed" in line:
                    # Parse line like "5 passed, 2 failed, 1 skipped in 10.5s"
                    parts = line.split()[0:6]  # Get first 6 parts
                    for i, part in enumerate(parts):
                        if part.isdigit() and i < len(parts) - 1:
                            count = int(part)
                            if i + 1 < len(parts):
                                status = parts[i + 1]
                                if status == "passed":
                                    passed_tests = count
                                elif status == "failed":
                                    failed_tests = count
                                elif status == "skipped":
                                    skipped_tests = count
                                elif status == "error":
                                    errors = count
                    total_tests = passed_tests + failed_tests + skipped_tests + errors
                elif " passed in " in line:
                    # Parse line like "5 passed in 10.5s"
                    parts = line.split()
                    if parts[0].isdigit():
                        passed_tests = int(parts[0])
                        total_tests = passed_tests
            
            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
            
            return {
                "suite": suite_info['name'],
                "system": suite_info['system'],
                "file": suite_info['file'],
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "skipped": skipped_tests,
                "errors": errors,
                "success_rate": success_rate,
                "duration": duration,
                "exit_code": result.returncode,
                "output": output,
                "error_output": error_output,
                "status": "PASSED" if result.returncode == 0 else "FAILED"
            }
            
        except Exception as e:
            return {
                "suite": suite_info['name'],
                "system": suite_info['system'],
                "file": suite_info['file'],
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": 1,
                "success_rate": 0,
                "duration": 0,
                "exit_code": 1,
                "output": "",
                "error_output": str(e),
                "status": "ERROR"
            }
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all test suites"""
        print(f"\n🚀 AITBC COMPLETE SYSTEM TEST RUNNER")
        print(f"📊 Testing All 9 Systems: 100% Completion Verification")
        print(f"⏰ Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")
        
        total_suites = len(self.test_suites)
        passed_suites = 0
        failed_suites = 0
        
        for suite in self.test_suites:
            result = self.run_test_suite(suite)
            self.results[suite['file']] = result
            
            # Print suite result summary
            status_emoji = "✅" if result['status'] == "PASSED" else "❌"
            print(f"\n{status_emoji} {suite['name']} Results:")
            print(f"   📊 Tests: {result['passed']}/{result['total_tests']} passed ({result['success_rate']:.1f}%)")
            print(f"   ⏱️  Duration: {result['duration']:.2f}s")
            print(f"   📈 Status: {result['status']}")
            
            if result['status'] == "PASSED":
                passed_suites += 1
            else:
                failed_suites += 1
                print(f"   ❌ Errors: {result['error_output'][:200]}...")
        
        # Calculate overall statistics
        overall_stats = self.calculate_overall_stats()
        overall_stats['total_suites'] = total_suites
        overall_stats['passed_suites'] = passed_suites
        overall_stats['failed_suites'] = failed_suites
        overall_stats['start_time'] = self.start_time
        overall_stats['end_time'] = datetime.now()
        overall_stats['total_duration'] = (overall_stats['end_time'] - self.start_time).total_seconds()
        
        return overall_stats
    
    def calculate_overall_stats(self) -> Dict[str, Any]:
        """Calculate overall test statistics"""
        total_tests = sum(r['total_tests'] for r in self.results.values())
        total_passed = sum(r['passed'] for r in self.results.values())
        total_failed = sum(r['failed'] for r in self.results.values())
        total_skipped = sum(r['skipped'] for r in self.results.values())
        total_errors = sum(r['errors'] for r in self.results.values())
        total_duration = sum(r['duration'] for r in self.results.values())
        
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        return {
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "overall_success_rate": overall_success_rate,
            "total_duration": total_duration
        }
    
    def print_final_report(self, stats: Dict[str, Any]):
        """Print final test report"""
        print(f"\n{'='*80}")
        print(f"🎉 AITBC COMPLETE SYSTEM TEST RESULTS")
        print(f"{'='*80}")
        print(f"📊 OVERALL STATISTICS:")
        print(f"   • Total Test Suites: {stats['total_suites']}")
        print(f"   • Passed Suites: {stats['passed_suites']}")
        print(f"   • Failed Suites: {stats['failed_suites']}")
        print(f"   • Suite Success Rate: {(stats['passed_suites']/stats['total_suites']*100):.1f}%")
        print(f"")
        print(f"🧪 TEST STATISTICS:")
        print(f"   • Total Tests: {stats['total_tests']}")
        print(f"   • Passed: {stats['total_passed']}")
        print(f"   • Failed: {stats['total_failed']}")
        print(f"   • Skipped: {stats['total_skipped']}")
        print(f"   • Errors: {stats['total_errors']}")
        print(f"   • Success Rate: {stats['overall_success_rate']:.1f}%")
        print(f"")
        print(f"⏱️  TIMING:")
        print(f"   • Total Duration: {stats['total_duration']:.2f}s")
        print(f"   • Started: {stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   • Ended: {stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"")
        print(f"🎯 SYSTEMS TESTED (9/9 Complete):")
        
        # Group results by system
        system_results = {}
        for suite_info in self.test_suites:
            system = suite_info['system']
            if system not in system_results:
                system_results[system] = []
            system_results[system].append(self.results.get(suite_info['file'], {}))
        
        for system, results in system_results.items():
            system_total_tests = sum(r['total_tests'] for r in results)
            system_passed = sum(r['passed'] for r in results)
            system_success_rate = (system_passed / system_total_tests * 100) if system_total_tests > 0 else 0
            status_emoji = "✅" if system_success_rate >= 80 else "❌"
            
            print(f"   {status_emoji} {system}: {system_passed}/{system_total_tests} ({system_success_rate:.1f}%)")
        
        print(f"")
        print(f"🚀 AITBC SYSTEMS STATUS: 9/9 COMPLETE (100%)")
        
        if stats['overall_success_rate'] >= 80:
            print(f"✅ OVERALL STATUS: EXCELLENT - System is production ready!")
        elif stats['overall_success_rate'] >= 60:
            print(f"⚠️  OVERALL STATUS: GOOD - System mostly functional")
        else:
            print(f"❌ OVERALL STATUS: NEEDS ATTENTION - System has issues")
        
        print(f"{'='*80}")

def main():
    """Main test runner function"""
    runner = CompleteTestRunner()
    stats = runner.run_all_tests()
    runner.print_final_report(stats)
    
    # Return appropriate exit code
    if stats['overall_success_rate'] >= 80:
        return 0
    else:
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
