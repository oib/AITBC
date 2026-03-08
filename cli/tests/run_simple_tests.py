#!/usr/bin/env python3
"""
Simple CLI Test Runner - Tests all available commands
"""

import sys
import os
from pathlib import Path

# Add CLI to path
sys.path.insert(0, '/opt/aitbc/cli')

from click.testing import CliRunner
from aitbc_cli.main_minimal import cli

def test_command(command_name, subcommand=None):
    """Test a specific command"""
    runner = CliRunner()
    
    if subcommand:
        result = runner.invoke(cli, [command_name, subcommand, '--help'])
    else:
        result = runner.invoke(cli, [command_name, '--help'])
    
    return result.exit_code == 0, len(result.output) > 0

def run_all_tests():
    """Run tests for all available commands"""
    print("🚀 AITBC CLI Comprehensive Test Runner")
    print("=" * 50)
    
    # Test main help
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    print(f"✓ Main Help: {'PASS' if result.exit_code == 0 else 'FAIL'}")
    
    # Test core commands
    commands = [
        'version',
        'config-show',
        'wallet',
        'config', 
        'blockchain',
        'compliance'
    ]
    
    passed = 0
    total = len(commands) + 1
    
    for cmd in commands:
        success, has_output = test_command(cmd)
        status = "PASS" if success else "FAIL"
        print(f"✓ {cmd}: {status}")
        if success:
            passed += 1
    
    # Test compliance subcommands
    compliance_subcommands = ['list-providers', 'kyc-submit', 'aml-screen']
    for subcmd in compliance_subcommands:
        success, has_output = test_command('compliance', subcmd)
        status = "PASS" if success else "FAIL"
        print(f"✓ compliance {subcmd}: {status}")
        total += 1
        if success:
            passed += 1
    
    print("=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
