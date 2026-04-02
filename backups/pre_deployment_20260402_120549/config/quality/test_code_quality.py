#!/usr/bin/env python3
"""
Quick test to verify code quality tools are working properly
"""
import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n🔍 {description}")
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/opt/aitbc")
        if result.returncode == 0:
            print(f"✅ {description} - PASSED")
            return True
        else:
            print(f"❌ {description} - FAILED")
            print(f"Error output: {result.stderr[:500]}")
            return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {e}")
        return False

def main():
    """Test code quality tools"""
    print("🚀 Testing AITBC Code Quality Setup")
    print("=" * 50)
    
    tests = [
        (["/opt/aitbc/venv/bin/black", "--check", "--diff", "apps/coordinator-api/src/app/routers/"], "Black formatting check"),
        (["/opt/aitbc/venv/bin/isort", "--check-only", "apps/coordinator-api/src/app/routers/"], "Isort import check"),
        (["/opt/aitbc/venv/bin/ruff", "check", "apps/coordinator-api/src/app/routers/"], "Ruff linting"),
        (["/opt/aitbc/venv/bin/mypy", "--ignore-missing-imports", "apps/coordinator-api/src/app/routers/"], "MyPy type checking"),
        (["/opt/aitbc/venv/bin/bandit", "-r", "apps/coordinator-api/src/app/routers/", "-f", "json"], "Bandit security check"),
    ]
    
    results = []
    for cmd, desc in tests:
        results.append(run_command(cmd, desc))
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Summary: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All code quality checks are working!")
        return 0
    else:
        print("⚠️  Some checks failed - review the output above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
