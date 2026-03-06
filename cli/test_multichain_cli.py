#!/usr/bin/env python3
"""
Multi-Chain CLI Test Script

This script tests the multi-chain wallet functionality through the CLI
to validate that the wallet-to-chain connection works correctly.
"""

import subprocess
import json
import time
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

def parse_json_output(output):
    """Parse JSON output from CLI command"""
    try:
        # Find JSON in output (might be mixed with other text)
        lines = output.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                return json.loads(line)
        return None
    except json.JSONDecodeError:
        return None

def test_chain_status():
    """Test chain status command"""
    print("🔍 Testing chain status...")
    
    stdout, stderr, code = run_cli_command("wallet --use-daemon chain status")
    
    if code == 0:
        data = parse_json_output(stdout)
        if data:
            print(f"✅ Chain status retrieved successfully")
            print(f"   Total chains: {data.get('total_chains', 'N/A')}")
            print(f"   Active chains: {data.get('active_chains', 'N/A')}")
            print(f"   Total wallets: {data.get('total_wallets', 'N/A')}")
            return True
        else:
            print("❌ Failed to parse chain status JSON")
            return False
    else:
        print(f"❌ Chain status command failed (code: {code})")
        print(f"   Error: {stderr}")
        return False

def test_chain_list():
    """Test chain list command"""
    print("\n🔍 Testing chain list...")
    
    stdout, stderr, code = run_cli_command("wallet --use-daemon chain list")
    
    if code == 0:
        data = parse_json_output(stdout)
        if data and 'chains' in data:
            print(f"✅ Chain list retrieved successfully")
            print(f"   Found {len(data['chains'])} chains:")
            for chain in data['chains']:
                print(f"   - {chain['chain_id']}: {chain['name']} ({chain['status']})")
            return True
        else:
            print("❌ Failed to parse chain list JSON")
            return False
    else:
        print(f"❌ Chain list command failed (code: {code})")
        print(f"   Error: {stderr}")
        return False

def test_chain_create():
    """Test chain creation"""
    print("\n🔍 Testing chain creation...")
    
    # Create a test chain
    chain_id = "test-cli-chain"
    chain_name = "Test CLI Chain"
    coordinator_url = "http://localhost:8099"
    api_key = "test-api-key"
    
    command = f"wallet --use-daemon chain create {chain_id} '{chain_name}' {coordinator_url} {api_key}"
    stdout, stderr, code = run_cli_command(command)
    
    if code == 0:
        data = parse_json_output(stdout)
        if data and data.get('chain_id') == chain_id:
            print(f"✅ Chain '{chain_id}' created successfully")
            print(f"   Name: {data.get('name')}")
            print(f"   Status: {data.get('status')}")
            return True
        else:
            print("❌ Failed to parse chain creation JSON")
            return False
    else:
        print(f"❌ Chain creation command failed (code: {code})")
        print(f"   Error: {stderr}")
        return False

def test_wallet_in_chain():
    """Test creating wallet in specific chain"""
    print("\n🔍 Testing wallet creation in chain...")
    
    # Create wallet in ait-devnet chain
    wallet_name = "test-cli-wallet"
    chain_id = "ait-devnet"
    
    command = f"wallet --use-daemon create-in-chain {chain_id} {wallet_name} --no-encrypt"
    stdout, stderr, code = run_cli_command(command)
    
    if code == 0:
        data = parse_json_output(stdout)
        if data and data.get('wallet_name') == wallet_name:
            print(f"✅ Wallet '{wallet_name}' created in chain '{chain_id}'")
            print(f"   Address: {data.get('address')}")
            print(f"   Public key: {data.get('public_key')[:20]}...")
            return True
        else:
            print("❌ Failed to parse wallet creation JSON")
            return False
    else:
        print(f"❌ Wallet creation command failed (code: {code})")
        print(f"   Error: {stderr}")
        return False

def test_chain_wallets():
    """Test listing wallets in chain"""
    print("\n🔍 Testing wallet listing in chain...")
    
    chain_id = "ait-devnet"
    command = f"wallet --use-daemon chain wallets {chain_id}"
    stdout, stderr, code = run_cli_command(command)
    
    if code == 0:
        data = parse_json_output(stdout)
        if data and 'wallets' in data:
            print(f"✅ Retrieved {len(data['wallets'])} wallets from chain '{chain_id}'")
            for wallet in data['wallets']:
                print(f"   - {wallet['wallet_name']}: {wallet['address']}")
            return True
        else:
            print("❌ Failed to parse chain wallets JSON")
            return False
    else:
        print(f"❌ Chain wallets command failed (code: {code})")
        print(f"   Error: {stderr}")
        return False

def test_wallet_balance():
    """Test wallet balance in chain"""
    print("\n🔍 Testing wallet balance in chain...")
    
    wallet_name = "test-cli-wallet"
    chain_id = "ait-devnet"
    
    command = f"wallet --use-daemon chain balance {chain_id} {wallet_name}"
    stdout, stderr, code = run_cli_command(command)
    
    if code == 0:
        data = parse_json_output(stdout)
        if data and 'balance' in data:
            print(f"✅ Retrieved balance for wallet '{wallet_name}' in chain '{chain_id}'")
            print(f"   Balance: {data.get('balance')}")
            return True
        else:
            print("❌ Failed to parse wallet balance JSON")
            return False
    else:
        print(f"❌ Wallet balance command failed (code: {code})")
        print(f"   Error: {stderr}")
        return False

def test_wallet_info():
    """Test wallet info in chain"""
    print("\n🔍 Testing wallet info in chain...")
    
    wallet_name = "test-cli-wallet"
    chain_id = "ait-devnet"
    
    command = f"wallet --use-daemon chain info {chain_id} {wallet_name}"
    stdout, stderr, code = run_cli_command(command)
    
    if code == 0:
        data = parse_json_output(stdout)
        if data and data.get('wallet_name') == wallet_name:
            print(f"✅ Retrieved info for wallet '{wallet_name}' in chain '{chain_id}'")
            print(f"   Address: {data.get('address')}")
            print(f"   Chain: {data.get('chain_id')}")
            return True
        else:
            print("❌ Failed to parse wallet info JSON")
            return False
    else:
        print(f"❌ Wallet info command failed (code: {code})")
        print(f"   Error: {stderr}")
        return False

def test_daemon_availability():
    """Test if wallet daemon is available"""
    print("🔍 Testing daemon availability...")
    
    stdout, stderr, code = run_cli_command("wallet daemon status")
    
    if code == 0 and "Wallet daemon is available" in stdout:
        print("✅ Wallet daemon is running and available")
        return True
    else:
        print(f"❌ Wallet daemon not available (code: {code})")
        print(f"   Error: {stderr}")
        return False

def main():
    """Run all multi-chain CLI tests"""
    print("🚀 Starting Multi-Chain CLI Tests")
    print("=" * 50)
    
    # Test results
    results = {}
    
    # Test 1: Daemon availability
    results['daemon'] = test_daemon_availability()
    
    if not results['daemon']:
        print("\n❌ Wallet daemon is not available. Please start the daemon first.")
        print("   Note: For testing purposes, we can continue without the daemon to validate CLI structure.")
        return False
    
    # Test 2: Chain operations
    results['chain_status'] = test_chain_status()
    results['chain_list'] = test_chain_list()
    results['chain_create'] = test_chain_create()
    
    # Test 3: Wallet operations in chains
    results['wallet_create'] = test_wallet_in_chain()
    results['chain_wallets'] = test_chain_wallets()
    results['wallet_balance'] = test_wallet_balance()
    results['wallet_info'] = test_wallet_info()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name.replace('_', ' ').title():<20}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Multi-chain CLI is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
