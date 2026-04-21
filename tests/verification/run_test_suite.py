#!/usr/bin/env python3
"""
Test suite runner for AITBC
"""

import sys
import argparse
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="AITBC Test Suite Runner")
    parser.add_argument(
        "--suite",
        choices=["unit", "integration", "e2e", "security", "all"],
        default="all",
        help="Test suite to run"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--marker",
        help="Run tests with specific marker (e.g., unit, integration)"
    )
    parser.add_argument(
        "--file",
        help="Run specific test file"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    pytest_cmd = ["python", "-m", "pytest"]
    
    # Add verbosity
    if args.verbose:
        pytest_cmd.append("-v")
    
    # Add coverage if requested
    if args.coverage:
        pytest_cmd.extend([
            "--cov=apps",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing"
        ])
    
    # Add parallel execution if requested
    if args.parallel:
        pytest_cmd.extend(["-n", "auto"])
    
    # Determine which tests to run
    test_paths = []
    
    if args.file:
        test_paths.append(args.file)
    elif args.marker:
        pytest_cmd.extend(["-m", args.marker])
    elif args.suite == "unit":
        test_paths.append("tests/unit/")
    elif args.suite == "integration":
        test_paths.append("tests/integration/")
    elif args.suite == "e2e":
        test_paths.append("tests/e2e/")
        # E2E tests might need additional setup
        pytest_cmd.extend(["--driver=Chrome"])
    elif args.suite == "security":
        pytest_cmd.extend(["-m", "security"])
    else:  # all
        test_paths.append("tests/")
    
    # Add test paths to command
    pytest_cmd.extend(test_paths)
    
    # Add pytest configuration
    pytest_cmd.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    # Run the tests
    success = run_command(pytest_cmd, f"{args.suite.title()} Test Suite")
    
    if success:
        print(f"\n✅ {args.suite.title()} tests passed!")
        
        if args.coverage:
            print("\n📊 Coverage report generated in htmlcov/index.html")
    else:
        print(f"\n❌ {args.suite.title()} tests failed!")
        sys.exit(1)
    
    # Additional checks
    if args.suite in ["all", "integration"]:
        print("\n🔍 Running integration test checks...")
        # Add any integration-specific checks here
    
    if args.suite in ["all", "e2e"]:
        print("\n🌐 Running E2E test checks...")
        # Add any E2E-specific checks here
    
    if args.suite in ["all", "security"]:
        print("\n🔒 Running security scan...")
        # Run security scan
        security_cmd = ["bandit", "-r", "apps/"]
        run_command(security_cmd, "Security Scan")
        
        # Run dependency check
        deps_cmd = ["safety", "check"]
        run_command(deps_cmd, "Dependency Security Check")


if __name__ == "__main__":
    main()
