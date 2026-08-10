#!/usr/bin/env python3
"""Simple CLI test runner that uses the virtual environment."""

import subprocess
import sys
from pathlib import Path


def run_cli_test():
    """Run basic CLI functionality tests."""
    print("🧪 Running CLI Tests with Virtual Environment...")

    # Set up environment
    cli_dir = Path(__file__).resolve().parent.parent
    cli_bin = "aitbc"  # Will be in PATH from virtual environment

    def run_command(*args):
        return subprocess.run(
            [cli_bin, *args],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cli_dir),
        )

    # Test 1: CLI help command
    print("\n1. Testing CLI help command...")
    try:
        result = run_command("--help")

        if result.returncode == 0 and "AITBC CLI" in result.stdout:
            print("✅ CLI help command working")
        else:
            print(f"❌ CLI help command failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ CLI help command error: {e}")
        return False

    # Test 2: CLI list command (optional - skip if no blockchain node)
    print("\n2. Testing CLI list command...")
    try:
        result = run_command("wallet", "list")

        if result.returncode == 0:
            print("✅ CLI list command working")
        elif (
            "Connection refused" in result.stderr
            or "Failed to establish" in result.stderr
            or "timeout" in str(result.stderr).lower()
        ):
            print("⚠️ CLI list command skipped (no blockchain node available)")
            print("   This is expected in CI environments without a running blockchain node")
        else:
            print(f"❌ CLI list command failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("⚠️ CLI list command timed out (no blockchain node available)")
        print("   This is expected in CI environments without a running blockchain node")
    except Exception as e:
        print(f"❌ CLI list command error: {e}")
        return False

    # Test 3: CLI chain command (optional - skip if no blockchain node)
    print("\n3. Testing CLI chain command...")
    try:
        result = run_command("chain", "status")

        if result.returncode == 0:
            print("✅ CLI chain command working")
        elif "Connection refused" in result.stderr or "Failed to establish" in result.stderr:
            print("⚠️ CLI chain command skipped (no blockchain node available)")
            print("   This is expected in CI environments without a running blockchain node")
        else:
            print(f"❌ CLI chain command failed: {result.stderr or result.stdout}")
            return False
    except Exception as e:
        print(f"❌ CLI chain command error: {e}")
        return False

    # Test 4: CLI invalid command handling
    print("\n4. Testing CLI invalid command handling...")
    try:
        result = run_command("invalid-command")

        if result.returncode != 0:
            print("✅ CLI invalid command handling working")
        else:
            print("❌ CLI invalid command should have failed")
            return False
    except Exception as e:
        print(f"❌ CLI invalid command error: {e}")
        return False

    print("\n✅ All CLI tests passed!")
    return True


if __name__ == "__main__":
    success = run_cli_test()
    sys.exit(0 if success else 1)
