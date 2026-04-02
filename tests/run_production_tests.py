#!/usr/bin/env python3
"""
AITBC Production Test Runner
Runs all production test suites for the 100% completed AITBC system
"""

import sys
import subprocess
import os
from pathlib import Path

def run_test_suite(test_file: str, description: str) -> bool:
    """Run a single test suite and return success status"""
    print(f"\n🧪 Running {description}")
    print(f"📁 File: {test_file}")
    print("=" * 60)
    
    try:
        # Change to the correct directory
        test_dir = Path(__file__).parent
        test_path = test_dir / "production" / test_file
        
        # Run the test
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            str(test_path), "-v", "--tb=short"
        ], capture_output=True, text=True, cwd=test_dir.parent.parent)
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        success = result.returncode == 0
        if success:
            print(f"✅ {description}: PASSED")
        else:
            print(f"❌ {description}: FAILED")
        
        return success
        
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return False

def main():
    """Run all production test suites"""
    print("🎉 AITBC Production Test Runner")
    print("=" * 60)
    print("🎯 Project Status: 100% COMPLETED (v0.3.0)")
    print("📊 Running all production test suites...")
    
    # Production test suites
    test_suites = [
        ("test_jwt_authentication.py", "JWT Authentication & RBAC"),
        ("test_production_monitoring.py", "Production Monitoring & Alerting"),
        ("test_type_safety.py", "Type Safety & Validation"),
        ("test_advanced_features.py", "Advanced Features & AI/ML"),
        ("test_complete_system_integration.py", "Complete System Integration")
    ]
    
    results = []
    total_tests = 0
    passed_tests = 0
    
    for test_file, description in test_suites:
        total_tests += 1
        success = run_test_suite(test_file, description)
        results.append((description, success))
        if success:
            passed_tests += 1
    
    # Print summary
    print("\n" + "=" * 60)
    print("🎯 PRODUCTION TEST RESULTS SUMMARY")
    print("=" * 60)
    
    for description, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status:<10} {description}")
    
    print(f"\n📊 Overall Results: {passed_tests}/{total_tests} test suites passed")
    success_rate = (passed_tests / total_tests) * 100
    print(f"🎯 Success Rate: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("\n🎉 ALL PRODUCTION TESTS PASSED!")
        print("🚀 AITBC System: 100% Production Ready")
        return 0
    else:
        print(f"\n⚠️  {total_tests - passed_tests} test suite(s) failed")
        print("🔧 Please review the failed tests above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
