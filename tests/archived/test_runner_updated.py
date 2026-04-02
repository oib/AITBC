#!/usr/bin/env python3
"""
Updated Test Runner for AITBC Agent Systems
Includes all test phases and API integration tests
"""

import subprocess
import sys
import os
from pathlib import Path
import time

def run_test_suite():
    """Run complete test suite"""
    base_dir = Path(__file__).parent
    
    print("=" * 80)
    print("AITBC AGENT SYSTEMS - COMPLETE TEST SUITE")
    print("=" * 80)
    
    test_suites = [
        {
            "name": "Agent Coordinator Communication Tests",
            "path": base_dir / "../apps/agent-coordinator/tests/test_communication_fixed.py",
            "type": "unit"
        },
        {
            "name": "Agent Coordinator API Tests",
            "path": base_dir / "test_agent_coordinator_api.py",
            "type": "integration"
        },
        {
            "name": "Phase 1: Consensus Tests",
            "path": base_dir / "phase1/consensus/test_consensus.py",
            "type": "phase"
        },
        {
            "name": "Phase 3: Decision Framework Tests",
            "path": base_dir / "phase3/test_decision_framework.py",
            "type": "phase"
        },
        {
            "name": "Phase 4: Autonomous Decision Making Tests",
            "path": base_dir / "phase4/test_autonomous_decision_making.py",
            "type": "phase"
        },
        {
            "name": "Phase 5: Vision Integration Tests",
            "path": base_dir / "phase5/test_vision_integration.py",
            "type": "phase"
        }
    ]
    
    results = {}
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    
    for suite in test_suites:
        print(f"\n{'-' * 60}")
        print(f"Running: {suite['name']}")
        print(f"Type: {suite['type']}")
        print(f"{'-' * 60}")
        
        if not suite['path'].exists():
            print(f"❌ Test file not found: {suite['path']}")
            results[suite['name']] = {
                'status': 'skipped',
                'reason': 'file_not_found'
            }
            continue
        
        try:
            # Run the test suite
            start_time = time.time()
            result = subprocess.run([
                sys.executable, '-m', 'pytest',
                str(suite['path']),
                '-v',
                '--tb=short',
                '--no-header'
            ], capture_output=True, text=True, cwd=base_dir)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Parse results
            output_lines = result.stdout.split('\n')
            passed = 0
            failed = 0
            skipped = 0
            errors = 0
            
            for line in output_lines:
                if ' passed' in line and ' failed' in line:
                    # Parse pytest summary line
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.isdigit() and i > 0:
                            if 'passed' in parts[i+1]:
                                passed = int(part)
                            elif 'failed' in parts[i+1]:
                                failed = int(part)
                            elif 'skipped' in parts[i+1]:
                                skipped = int(part)
                            elif 'error' in parts[i+1]:
                                errors = int(part)
                elif ' passed in ' in line:
                    # Single test passed
                    passed = 1
                elif ' failed in ' in line:
                    # Single test failed
                    failed = 1
                elif ' skipped in ' in line:
                    # Single test skipped
                    skipped = 1
            
            suite_total = passed + failed + errors
            suite_passed = passed
            suite_failed = failed + errors
            suite_skipped = skipped
            
            # Update totals
            total_tests += suite_total
            total_passed += suite_passed
            total_failed += suite_failed
            total_skipped += suite_skipped
            
            # Store results
            results[suite['name']] = {
                'status': 'completed',
                'total': suite_total,
                'passed': suite_passed,
                'failed': suite_failed,
                'skipped': suite_skipped,
                'execution_time': execution_time,
                'returncode': result.returncode
            }
            
            # Print summary
            print(f"✅ Completed in {execution_time:.2f}s")
            print(f"📊 Results: {suite_passed} passed, {suite_failed} failed, {suite_skipped} skipped")
            
            if result.returncode != 0:
                print(f"❌ Some tests failed")
                if result.stderr:
                    print(f"Errors: {result.stderr[:200]}...")
            
        except Exception as e:
            print(f"❌ Error running test suite: {e}")
            results[suite['name']] = {
                'status': 'error',
                'error': str(e)
            }
    
    # Print final summary
    print("\n" + "=" * 80)
    print("FINAL TEST SUMMARY")
    print("=" * 80)
    
    print(f"Total Test Suites: {len(test_suites)}")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {total_passed} ({total_passed/total_tests*100:.1f}%)" if total_tests > 0 else "Passed: 0")
    print(f"Failed: {total_failed} ({total_failed/total_tests*100:.1f}%)" if total_tests > 0 else "Failed: 0")
    print(f"Skipped: {total_skipped} ({total_skipped/total_tests*100:.1f}%)" if total_tests > 0 else "Skipped: 0")
    
    print(f"\nSuite Details:")
    for name, result in results.items():
        print(f"\n{name}:")
        if result['status'] == 'completed':
            print(f"  Status: ✅ Completed")
            print(f"  Tests: {result['total']} (✅ {result['passed']}, ❌ {result['failed']}, ⏭️ {result['skipped']})")
            print(f"  Time: {result['execution_time']:.2f}s")
        elif result['status'] == 'skipped':
            print(f"  Status: ⏭️ Skipped ({result.get('reason', 'unknown')})")
        else:
            print(f"  Status: ❌ Error ({result.get('error', 'unknown')})")
    
    # Overall status
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n{'=' * 80}")
    if success_rate >= 90:
        print("🎉 EXCELLENT: Test suite passed with high success rate!")
    elif success_rate >= 75:
        print("✅ GOOD: Test suite passed with acceptable success rate!")
    elif success_rate >= 50:
        print("⚠️  WARNING: Test suite has significant failures!")
    else:
        print("❌ CRITICAL: Test suite has major issues!")
    
    print(f"Overall Success Rate: {success_rate:.1f}%")
    print("=" * 80)
    
    return results

if __name__ == '__main__':
    run_test_suite()
