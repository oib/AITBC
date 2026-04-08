#!/usr/bin/env python3
"""Simple CLI test runner that uses the virtual environment."""

import subprocess
import sys
import os
from pathlib import Path

def run_cli_test():
    """Run basic CLI functionality tests."""
    print("🧪 Running CLI Tests with Virtual Environment...")
    
    # Set up environment
    cli_dir = Path(__file__).parent.parent
    cli_bin = "/opt/aitbc/aitbc-cli"
    
    # Test 1: CLI help command
    print("\n1. Testing CLI help command...")
    try:
        result = subprocess.run(
            [cli_bin, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cli_dir)
        )
        
        if result.returncode == 0 and "AITBC CLI" in result.stdout:
            print("✅ CLI help command working")
        else:
            print(f"❌ CLI help command failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ CLI help command error: {e}")
        return False
    
    # Test 2: CLI list command
    print("\n2. Testing CLI list command...")
    try:
        result = subprocess.run(
            [cli_bin, "wallet", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cli_dir)
        )
        
        if result.returncode == 0:
            print("✅ CLI list command working")
        else:
            print(f"❌ CLI list command failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ CLI list command error: {e}")
        return False
    
    # Test 3: CLI blockchain command
    print("\n3. Testing CLI blockchain command...")
    try:
        result = subprocess.run(
            [cli_bin, "blockchain", "info"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cli_dir)
        )
        
        if result.returncode == 0:
            print("✅ CLI blockchain command working")
        else:
            print(f"❌ CLI blockchain command failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ CLI blockchain command error: {e}")
        return False
    
    # Test 4: CLI invalid command handling
    print("\n4. Testing CLI invalid command handling...")
    try:
        result = subprocess.run(
            [cli_bin, "invalid-command"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cli_dir)
        )
        
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
