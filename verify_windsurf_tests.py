#!/usr/bin/env python3
"""
Verify Windsurf test integration is working properly
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"Command: {cmd}")
    print('='*60)
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print("STDOUT:")
        print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    return result.returncode == 0

def main():
    print("🔍 Verifying Windsurf Test Integration")
    print("=" * 60)
    
    # Change to project directory
    os.chdir('/home/oib/windsurf/aitbc')
    
    tests = [
        ("pytest --collect-only tests/test_windsurf_integration.py", "Test Discovery"),
        ("pytest tests/test_windsurf_integration.py -v", "Run Simple Tests"),
        ("pytest --collect-only tests/ -q --no-cov", "Collect All Tests (without imports)"),
    ]
    
    all_passed = True
    
    for cmd, desc in tests:
        if not run_command(cmd, desc):
            all_passed = False
            print(f"❌ Failed: {desc}")
        else:
            print(f"✅ Passed: {desc}")
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed! Windsurf integration is working.")
        print("\nTo use in Windsurf:")
        print("1. Open the Testing panel (beaker icon)")
        print("2. Tests should be automatically discovered")
        print("3. Click play button to run tests")
        print("4. Use F5 to debug tests")
    else:
        print("❌ Some tests failed. Check the output above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
