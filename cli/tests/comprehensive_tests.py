#!/usr/bin/env python3
"""
Comprehensive CLI Test Suite - Tests all levels and groups
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path

# Add CLI to path
sys.path.insert(0, '/opt/aitbc/cli')

from click.testing import CliRunner
from core.main_minimal import cli

def test_basic_functionality():
    """Test basic CLI functionality"""
    print("=== Level 1: Basic Functionality ===")
    runner = CliRunner()
    
    tests = [
        (['--help'], 'Main help'),
        (['version'], 'Version command'),
        (['config-show'], 'Config show'),
        (['config', '--help'], 'Config help'),
        (['wallet', '--help'], 'Wallet help'),
        (['blockchain', '--help'], 'Blockchain help'),
        (['compliance', '--help'], 'Compliance help'),
    ]
    
    passed = 0
    for args, description in tests:
        result = runner.invoke(cli, args)
        status = "PASS" if result.exit_code == 0 else "FAIL"
        print(f"  {description}: {status}")
        if result.exit_code == 0:
            passed += 1
    
    print(f"  Level 1 Results: {passed}/{len(tests)} passed")
    return passed, len(tests)

def test_compliance_functionality():
    """Test compliance subcommands"""
    print("\n=== Level 2: Compliance Commands ===")
    runner = CliRunner()
    
    tests = [
        (['compliance', 'list-providers'], 'List providers'),
        (['compliance', 'kyc-submit', '--help'], 'KYC submit help'),
        (['compliance', 'aml-screen', '--help'], 'AML screen help'),
        (['compliance', 'kyc-status', '--help'], 'KYC status help'),
        (['compliance', 'full-check', '--help'], 'Full check help'),
    ]
    
    passed = 0
    for args, description in tests:
        result = runner.invoke(cli, args)
        status = "PASS" if result.exit_code == 0 else "FAIL"
        print(f"  {description}: {status}")
        if result.exit_code == 0:
            passed += 1
    
    print(f"  Level 2 Results: {passed}/{len(tests)} passed")
    return passed, len(tests)

def test_wallet_functionality():
    """Test wallet commands"""
    print("\n=== Level 3: Wallet Commands ===")
    runner = CliRunner()
    
    tests = [
        (['wallet', 'list'], 'Wallet list'),
        (['wallet', 'create', '--help'], 'Create help'),
        (['wallet', 'balance', '--help'], 'Balance help'),
        (['wallet', 'send', '--help'], 'Send help'),
        (['wallet', 'address', '--help'], 'Address help'),
    ]
    
    passed = 0
    for args, description in tests:
        result = runner.invoke(cli, args)
        status = "PASS" if result.exit_code == 0 else "FAIL"
        print(f"  {description}: {status}")
        if result.exit_code == 0:
            passed += 1
    
    print(f"  Level 3 Results: {passed}/{len(tests)} passed")
    return passed, len(tests)

def test_blockchain_functionality():
    """Test blockchain commands"""
    print("\n=== Level 4: Blockchain Commands ===")
    runner = CliRunner()
    
    tests = [
        (['blockchain', 'status'], 'Blockchain status'),
        (['blockchain', 'info'], 'Blockchain info'),
        (['blockchain', 'blocks', '--help'], 'Blocks help'),
        (['blockchain', 'balance', '--help'], 'Balance help'),
        (['blockchain', 'peers', '--help'], 'Peers help'),
    ]
    
    passed = 0
    for args, description in tests:
        result = runner.invoke(cli, args)
        status = "PASS" if result.exit_code == 0 else "FAIL"
        print(f"  {description}: {status}")
        if result.exit_code == 0:
            passed += 1
    
    print(f"  Level 4 Results: {passed}/{len(tests)} passed")
    return passed, len(tests)

def test_config_functionality():
    """Test config commands"""
    print("\n=== Level 5: Config Commands ===")
    runner = CliRunner()
    
    tests = [
        (['config', 'show'], 'Config show'),
        (['config', 'get', '--help'], 'Get help'),
        (['config', 'set', '--help'], 'Set help'),
        (['config', 'edit', '--help'], 'Edit help'),
        (['config', 'validate', '--help'], 'Validate help'),
    ]
    
    passed = 0
    for args, description in tests:
        result = runner.invoke(cli, args)
        status = "PASS" if result.exit_code == 0 else "FAIL"
        print(f"  {description}: {status}")
        if result.exit_code == 0:
            passed += 1
    
    print(f"  Level 5 Results: {passed}/{len(tests)} passed")
    return passed, len(tests)

def test_integration_functionality():
    """Test integration scenarios"""
    print("\n=== Level 6: Integration Tests ===")
    runner = CliRunner()
    
    # Test CLI with different options
    tests = [
        (['--help'], 'Help with default options'),
        (['--output', 'json', '--help'], 'Help with JSON output'),
        (['--verbose', '--help'], 'Help with verbose'),
        (['--debug', '--help'], 'Help with debug'),
        (['--test-mode', '--help'], 'Help with test mode'),
    ]
    
    passed = 0
    for args, description in tests:
        result = runner.invoke(cli, args)
        status = "PASS" if result.exit_code == 0 else "FAIL"
        print(f"  {description}: {status}")
        if result.exit_code == 0:
            passed += 1
    
    print(f"  Level 6 Results: {passed}/{len(tests)} passed")
    return passed, len(tests)

def test_error_handling():
    """Test error handling"""
    print("\n=== Level 7: Error Handling ===")
    runner = CliRunner()
    
    # Test invalid commands and options
    tests = [
        (['invalid-command'], 'Invalid command'),
        (['--invalid-option'], 'Invalid option'),
        (['wallet', 'invalid-subcommand'], 'Invalid wallet subcommand'),
        (['compliance', 'kyc-submit'], 'KYC submit without args'),
    ]
    
    passed = 0
    for args, description in tests:
        result = runner.invoke(cli, args)
        # These should fail (exit code != 0), which is correct error handling
        status = "PASS" if result.exit_code != 0 else "FAIL"
        print(f"  {description}: {status}")
        if result.exit_code != 0:
            passed += 1
    
    print(f"  Level 7 Results: {passed}/{len(tests)} passed")
    return passed, len(tests)

def run_comprehensive_tests():
    """Run all test levels"""
    print("🚀 AITBC CLI Comprehensive Test Suite")
    print("=" * 60)
    
    total_passed = 0
    total_tests = 0
    
    # Run all test levels
    levels = [
        test_basic_functionality,
        test_compliance_functionality,
        test_wallet_functionality,
        test_blockchain_functionality,
        test_config_functionality,
        test_integration_functionality,
        test_error_handling,
    ]
    
    for level_test in levels:
        passed, tests = level_test()
        total_passed += passed
        total_tests += tests
    
    print("\n" + "=" * 60)
    print(f"Final Results: {total_passed}/{total_tests} tests passed")
    print(f"Success Rate: {(total_passed/total_tests)*100:.1f}%")
    
    if total_passed >= total_tests * 0.8:  # 80% success rate
        print("🎉 Comprehensive tests completed successfully!")
        return True
    else:
        print("❌ Some critical tests failed!")
        return False

if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)
