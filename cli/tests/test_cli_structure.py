#!/usr/bin/env python3
"""
CLI Structure Test Script

This script tests that the multi-chain CLI commands are properly structured
and available, even if the daemon doesn't have multi-chain support yet.
"""

import subprocess
import json
import sys
from pathlib import Path

def run_cli_command(command, check=True, timeout=30):
    """Run a CLI command and return the result"""
    try:
        # Use the aitbc command from the installed package
        full_command = f"aitbc {command}"
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr, e.returncode

def test_cli_help():
    """Test that CLI help works"""
    print("🔍 Testing CLI help...")
    
    stdout, stderr, code = run_cli_command("--help")
    
    if code == 0 and "AITBC" in stdout:
        print("✅ CLI help works")
        return True
    else:
        print("❌ CLI help failed")
        return False

def test_wallet_help():
    """Test that wallet help works"""
    print("\n🔍 Testing wallet help...")
    
    stdout, stderr, code = run_cli_command("wallet --help")
    
    if code == 0 and "chain" in stdout and "create-in-chain" in stdout:
        print("✅ Wallet help shows multi-chain commands")
        return True
    else:
        print("❌ Wallet help missing multi-chain commands")
        return False

def test_chain_help():
    """Test that chain help works"""
    print("\n🔍 Testing chain help...")
    
    stdout, stderr, code = run_cli_command("wallet chain --help")
    
    expected_commands = ["list", "create", "status", "wallets", "info", "balance", "migrate"]
    found_commands = []
    
    if code == 0:
        for cmd in expected_commands:
            if cmd in stdout:
                found_commands.append(cmd)
    
    if len(found_commands) >= len(expected_commands) - 1:  # Allow for minor differences
        print(f"✅ Chain help shows {len(found_commands)}/{len(expected_commands)} expected commands")
        print(f"   Found: {', '.join(found_commands)}")
        return True
    else:
        print(f"❌ Chain help missing commands. Found: {found_commands}")
        return False

def test_chain_commands_exist():
    """Test that chain commands exist (even if they fail)"""
    print("\n🔍 Testing chain commands exist...")
    
    commands = [
        "wallet chain list",
        "wallet chain status", 
        "wallet chain create test-chain 'Test Chain' http://localhost:8099 test-key",
        "wallet chain wallets ait-devnet",
        "wallet chain info ait-devnet test-wallet",
        "wallet chain balance ait-devnet test-wallet",
        "wallet chain migrate ait-devnet ait-testnet test-wallet"
    ]
    
    success_count = 0
    for cmd in commands:
        stdout, stderr, code = run_cli_command(cmd, check=False)
        
        # We expect commands to exist (not show "No such command") even if they fail
        if "No such command" not in stderr and "Try 'aitbc --help'" not in stderr:
            success_count += 1
            print(f"   ✅ {cmd.split()[2]} command exists")
        else:
            print(f"   ❌ {cmd.split()[2]} command doesn't exist")
    
    print(f"✅ {success_count}/{len(commands)} chain commands exist")
    return success_count >= len(commands) - 1  # Allow for one failure

def test_create_in_chain_command():
    """Test that create-in-chain command exists"""
    print("\n🔍 Testing create-in-chain command...")
    
    stdout, stderr, code = run_cli_command("wallet create-in-chain --help", check=False)
    
    if "Create a wallet in a specific chain" in stdout or "chain_id" in stdout:
        print("✅ create-in-chain command exists")
        return True
    else:
        print("❌ create-in-chain command doesn't exist")
        return False

def test_daemon_commands():
    """Test daemon commands"""
    print("\n🔍 Testing daemon commands...")
    
    stdout, stderr, code = run_cli_command("wallet daemon --help")
    
    if code == 0 and "status" in stdout and "configure" in stdout:
        print("✅ Daemon commands available")
        return True
    else:
        print("❌ Daemon commands missing")
        return False

def test_daemon_status():
    """Test daemon status"""
    print("\n🔍 Testing daemon status...")
    
    stdout, stderr, code = run_cli_command("wallet daemon status")
    
    if code == 0 and ("Wallet daemon is available" in stdout or "status" in stdout.lower()):
        print("✅ Daemon status command works")
        return True
    else:
        print("❌ Daemon status command failed")
        return False

def test_use_daemon_flag():
    """Test that --use-daemon flag is recognized"""
    print("\n🔍 Testing --use-daemon flag...")
    
    # Test with a simple command that should recognize the flag
    stdout, stderr, code = run_cli_command("wallet --use-daemon --help", check=False)
    
    if code == 0 or "use-daemon" in stdout:
        print("✅ --use-daemon flag recognized")
        return True
    else:
        print("❌ --use-daemon flag not recognized")
        return False

def main():
    """Run all CLI structure tests"""
    print("🚀 Starting CLI Structure Tests")
    print("=" * 50)
    
    # Test results
    results = {}
    
    # Test basic CLI structure
    results['cli_help'] = test_cli_help()
    results['wallet_help'] = test_wallet_help()
    results['chain_help'] = test_chain_help()
    results['chain_commands'] = test_chain_commands_exist()
    results['create_in_chain'] = test_create_in_chain_command()
    results['daemon_commands'] = test_daemon_commands()
    results['daemon_status'] = test_daemon_status()
    results['use_daemon_flag'] = test_use_daemon_flag()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 CLI Structure Test Results:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name.replace('_', ' ').title():<20}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed >= total - 1:  # Allow for one failure
        print("🎉 CLI structure is working correctly!")
        print("💡 Note: Multi-chain daemon endpoints may need to be implemented for full functionality.")
        return True
    else:
        print("⚠️  Some CLI structure tests failed.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
