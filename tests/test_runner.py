#!/usr/bin/env python3
"""
Simple Test Runner for AITBC

This script provides convenient commands for running tests with the new
pyproject.toml configuration. It's a thin wrapper around pytest that
provides common test patterns and helpful output.

Usage:
    python tests/test_runner.py                    # Run all fast tests
    python tests/test_runner.py --all              # Run all tests including slow
    python tests/test_runner.py --unit             # Run unit tests only
    python tests/test_runner.py --integration      # Run integration tests only
    python tests/test_runner.py --cli              # Run CLI tests only
    python tests/test_runner.py --coverage         # Run with coverage
    python tests/test_runner.py --performance      # Run performance tests
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_pytest(args, description):
    """Run pytest with given arguments."""
    print(f"🧪 {description}")
    print("=" * 50)
    
    cmd = ["python", "-m", "pytest"] + args
    
    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
        return result.returncode
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted")
        return 1
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="AITBC Test Runner - Simple wrapper around pytest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/test_runner.py                    # Run all fast tests
  python tests/test_runner.py --all              # Run all tests including slow
  python tests/test_runner.py --unit             # Run unit tests only
  python tests/test_runner.py --integration      # Run integration tests only
  python tests/test_runner.py --cli              # Run CLI tests only
  python tests/test_runner.py --coverage         # Run with coverage
  python tests/test_runner.py --performance      # Run performance tests
        """
    )
    
    # Test selection options
    test_group = parser.add_mutually_exclusive_group()
    test_group.add_argument("--all", action="store_true", help="Run all tests including slow ones")
    test_group.add_argument("--unit", action="store_true", help="Run unit tests only")
    test_group.add_argument("--integration", action="store_true", help="Run integration tests only")
    test_group.add_argument("--cli", action="store_true", help="Run CLI tests only")
    test_group.add_argument("--api", action="store_true", help="Run API tests only")
    test_group.add_argument("--blockchain", action="store_true", help="Run blockchain tests only")
    test_group.add_argument("--slow", action="store_true", help="Run slow tests only")
    test_group.add_argument("--performance", action="store_true", help="Run performance tests only")
    test_group.add_argument("--security", action="store_true", help="Run security tests only")
    
    # Additional options
    parser.add_argument("--coverage", action="store_true", help="Run with coverage reporting")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug mode (show collection)")
    parser.add_argument("--list", "-l", action="store_true", help="List available tests")
    parser.add_argument("--markers", action="store_true", help="Show available markers")
    
    # Allow passing through pytest arguments
    parser.add_argument("pytest_args", nargs="*", help="Additional pytest arguments")
    
    args = parser.parse_args()
    
    # Build pytest command
    pytest_args = []
    
    # Add coverage if requested
    if args.coverage:
        pytest_args.extend(["--cov=aitbc_cli", "--cov-report=term-missing"])
        if args.verbose:
            pytest_args.append("--cov-report=html")
    
    # Add verbosity
    if args.verbose:
        pytest_args.append("-v")
    
    # Add test selection markers
    if args.all:
        pytest_args.append("-m")  # No marker - run all tests
    elif args.unit:
        pytest_args.extend(["-m", "unit and not slow"])
    elif args.integration:
        pytest_args.extend(["-m", "integration and not slow"])
    elif args.cli:
        pytest_args.extend(["-m", "cli and not slow"])
    elif args.api:
        pytest_args.extend(["-m", "api and not slow"])
    elif args.blockchain:
        pytest_args.extend(["-m", "blockchain and not slow"])
    elif args.slow:
        pytest_args.extend(["-m", "slow"])
    elif args.performance:
        pytest_args.extend(["-m", "performance"])
    elif args.security:
        pytest_args.extend(["-m", "security"])
    else:
        # Default: run fast tests only
        pytest_args.extend(["-m", "unit or integration or cli or api or blockchain"])
        pytest_args.extend(["-m", "not slow"])
    
    # Add debug options
    if args.debug:
        pytest_args.append("--debug")
    
    # Add list/markers options
    if args.list:
        pytest_args.append("--collect-only")
    elif args.markers:
        pytest_args.append("--markers")
    
    # Add additional pytest arguments
    if args.pytest_args:
        pytest_args.extend(args.pytest_args)
    
    # Special handling for markers/list (don't run tests)
    if args.list or args.markers:
        return run_pytest(pytest_args, "Listing pytest information")
    
    # Run tests
    if args.all:
        description = "Running all tests (including slow)"
    elif args.unit:
        description = "Running unit tests"
    elif args.integration:
        description = "Running integration tests"
    elif args.cli:
        description = "Running CLI tests"
    elif args.api:
        description = "Running API tests"
    elif args.blockchain:
        description = "Running blockchain tests"
    elif args.slow:
        description = "Running slow tests"
    elif args.performance:
        description = "Running performance tests"
    elif args.security:
        description = "Running security tests"
    else:
        description = "Running fast tests (unit, integration, CLI, API, blockchain)"
    
    if args.coverage:
        description += " with coverage"
    
    return run_pytest(pytest_args, description)


if __name__ == "__main__":
    sys.exit(main())
