#!/usr/bin/env python3
"""
End-to-End Test Runner for Enhanced Services
Provides convenient interface for running different test suites
"""

import asyncio
import subprocess
import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Test suites configuration
TEST_SUITES = {
    "workflows": {
        "description": "Complete workflow tests",
        "files": ["test_enhanced_services_workflows.py"],
        "markers": ["e2e", "workflow"],
        "timeout": 300
    },
    "client_miner": {
        "description": "Client-to-miner pipeline tests",
        "files": ["test_client_miner_workflow.py"],
        "markers": ["e2e", "integration"],
        "timeout": 180
    },
    "performance": {
        "description": "Performance benchmark tests",
        "files": ["test_performance_benchmarks.py"],
        "markers": ["e2e", "performance"],
        "timeout": 600
    },
    "all": {
        "description": "All end-to-end tests",
        "files": ["test_*.py"],
        "markers": ["e2e"],
        "timeout": 900
    },
    "quick": {
        "description": "Quick smoke tests",
        "files": ["test_client_miner_workflow.py"],
        "markers": ["e2e"],
        "timeout": 120,
        "maxfail": 1
    }
}


def print_header(title: str):
    """Print formatted header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")


def print_warning(message: str):
    """Print warning message"""
    print(f"⚠️  {message}")


def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")


def check_services_health() -> bool:
    """Check if enhanced services are healthy before running tests"""
    print("🔍 Checking enhanced services health...")
    
    services = {
        "multimodal": 8002,
        "gpu_multimodal": 8003,
        "modality_optimization": 8004,
        "adaptive_learning": 8005,
        "marketplace_enhanced": 8006,
        "openclaw_enhanced": 8007
    }
    
    healthy_count = 0
    
    try:
        import httpx
        
        async def check_service(name: str, port: int) -> bool:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"http://localhost:{port}/health")
                    if response.status_code == 200:
                        print(f"✅ {name} (:{port}) - healthy")
                        return True
                    else:
                        print(f"❌ {name} (:{port}) - unhealthy: {response.status_code}")
                        return False
            except Exception as e:
                print(f"❌ {name} (:{port}) - unavailable: {e}")
                return False
        
        async def check_all_services():
            tasks = [check_service(name, port) for name, port in services.items()]
            results = await asyncio.gather(*tasks)
            return sum(results)
        
        healthy_count = asyncio.run(check_all_services())
        
    except ImportError:
        print("❌ httpx not available - cannot check services")
        return False
    
    print(f"📊 Services healthy: {healthy_count}/{len(services)}")
    
    if healthy_count < 4:  # Need at least 4 services for meaningful tests
        print_warning("Insufficient healthy services for comprehensive testing")
        return False
    
    return True


def run_pytest_command(suite_config: Dict[str, Any], verbose: bool = False, parallel: bool = False) -> int:
    """Run pytest with the given configuration"""
    
    # Build pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        "-v" if verbose else "-q",
        "--tb=short",
        "--color=yes"
    ]
    
    # Add markers
    if "markers" in suite_config:
        for marker in suite_config["markers"]:
            cmd.extend(["-m", marker])
    
    # Add maxfail if specified
    if "maxfail" in suite_config:
        cmd.extend(["--maxfail", str(suite_config["maxfail"])])
    
    # Add parallel execution if requested
    if parallel:
        cmd.extend(["-n", "auto"])
    
    # Add files
    if "files" in suite_config:
        cmd.extend(suite_config["files"])
    
    # Change to e2e test directory
    e2e_dir = Path(__file__).parent
    original_dir = Path.cwd()
    
    try:
        # Change to e2e directory
        import os
        os.chdir(e2e_dir)
        
        print(f"🚀 Running: {' '.join(cmd)}")
        print(f"📁 Working directory: {e2e_dir}")
        
        # Run pytest
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=False)
        duration = time.time() - start_time
        
        print(f"\n⏱️  Test duration: {duration:.1f}s")
        
        return result.returncode
        
    finally:
        # Restore original directory
        os.chdir(original_dir)


def run_test_suite(suite_name: str, verbose: bool = False, parallel: bool = False, skip_health_check: bool = False) -> int:
    """Run a specific test suite"""
    
    if suite_name not in TEST_SUITES:
        print_error(f"Unknown test suite: {suite_name}")
        print(f"Available suites: {', '.join(TEST_SUITES.keys())}")
        return 1
    
    suite_config = TEST_SUITES[suite_name]
    
    print_header(f"Running {suite_name.upper()} Test Suite")
    print(f"Description: {suite_config['description']}")
    
    # Check services health (unless skipped)
    if not skip_health_check:
        if not check_services_health():
            print_warning("Services health check failed - proceeding anyway")
    
    # Run the tests
    exit_code = run_pytest_command(suite_config, verbose, parallel)
    
    # Report results
    if exit_code == 0:
        print_success(f"{suite_name.upper()} test suite completed successfully!")
    else:
        print_error(f"{suite_name.upper()} test suite failed with exit code {exit_code}")
    
    return exit_code


def list_test_suites():
    """List available test suites"""
    print_header("Available Test Suites")
    
    for name, config in TEST_SUITES.items():
        print(f"📋 {name}")
        print(f"   Description: {config['description']}")
        print(f"   Files: {', '.join(config['files'])}")
        print(f"   Markers: {', '.join(config.get('markers', []))}")
        print(f"   Timeout: {config.get('timeout', 300)}s")
        print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run AITBC Enhanced Services End-to-End Tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_e2e_tests.py workflows          # Run workflow tests
  python run_e2e_tests.py performance -v      # Run performance tests with verbose output
  python run_e2e_tests.py all --parallel      # Run all tests in parallel
  python run_e2e_tests.py quick --skip-health # Run quick tests without health check
  python run_e2e_tests.py --list              # List available test suites
        """
    )
    
    parser.add_argument(
        "suite",
        nargs="?",
        default="quick",
        help="Test suite to run (default: quick)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Run tests in parallel (requires pytest-xdist)"
    )
    
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip services health check"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available test suites and exit"
    )
    
    args = parser.parse_args()
    
    # List test suites if requested
    if args.list:
        list_test_suites()
        return 0
    
    # Check dependencies
    try:
        import pytest
        print_success("pytest available")
    except ImportError:
        print_error("pytest not available - please install with: pip install pytest")
        return 1
    
    if args.parallel:
        try:
            import pytest_xdist
            print_success("pytest-xdist available for parallel execution")
        except ImportError:
            print_warning("pytest-xdist not available - running sequentially")
            args.parallel = False
    
    # Run the requested test suite
    exit_code = run_test_suite(
        args.suite,
        verbose=args.verbose,
        parallel=args.parallel,
        skip_health_check=args.skip_health
    )
    
    return exit_code


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("\nTest execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
