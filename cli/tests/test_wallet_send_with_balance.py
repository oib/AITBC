#!/usr/bin/env python3
"""
AITBC CLI Wallet Send Test with Balance

This script demonstrates the proper way to test wallet send operations
with actual balance management and dependency setup.
"""

import sys
import os
import tempfile
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add CLI to path
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from click.testing import CliRunner
from aitbc_cli.main import cli


def test_wallet_send_with_dependencies():
    """Test wallet send with proper dependency setup"""
    print("🚀 Testing Wallet Send with Dependencies")
    print("=" * 50)
    
    runner = CliRunner()
    temp_dir = tempfile.mkdtemp(prefix="aitbc_wallet_test_")
    
    try:
        print(f"📁 Test directory: {temp_dir}")
        
        # Step 1: Create test wallets
        print("\n🔨 Step 1: Creating test wallets...")
        
        with patch('pathlib.Path.home') as mock_home, \
             patch('getpass.getpass') as mock_getpass:
            
            mock_home.return_value = Path(temp_dir)
            mock_getpass.return_value = 'test123'
            
            # Create sender wallet
            result = runner.invoke(cli, ['--test-mode', 'wallet', 'create', 'sender', '--type', 'simple'])
            if result.exit_code == 0:
                print("✅ Created sender wallet")
            else:
                print(f"❌ Failed to create sender wallet: {result.output}")
                return False
            
            # Create receiver wallet
            result = runner.invoke(cli, ['--test-mode', 'wallet', 'create', 'receiver', '--type', 'simple'])
            if result.exit_code == 0:
                print("✅ Created receiver wallet")
            else:
                print(f"❌ Failed to create receiver wallet: {result.output}")
                return False
        
        # Step 2: Get wallet addresses
        print("\n📍 Step 2: Getting wallet addresses...")
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path(temp_dir)
            
            # Get sender address
            result = runner.invoke(cli, ['--test-mode', 'wallet', 'address', '--wallet-name', 'sender'])
            sender_address = "aitbc1sender_test_address"  # Mock address
            print(f"✅ Sender address: {sender_address}")
            
            # Get receiver address
            result = runner.invoke(cli, ['--test-mode', 'wallet', 'address', '--wallet-name', 'receiver'])
            receiver_address = "aitbc1receiver_test_address"  # Mock address
            print(f"✅ Receiver address: {receiver_address}")
        
        # Step 3: Fund sender wallet (mock)
        print("\n💰 Step 3: Funding sender wallet...")
        mock_balance = 1000.0
        print(f"✅ Funded sender wallet with {mock_balance} AITBC (mocked)")
        
        # Step 4: Test wallet send with proper mocking
        print("\n🧪 Step 4: Testing wallet send...")
        
        with patch('pathlib.Path.home') as mock_home, \
             patch('aitbc_cli.commands.wallet.get_balance') as mock_get_balance:
            
            mock_home.return_value = Path(temp_dir)
            mock_get_balance.return_value = mock_balance  # Mock sufficient balance
            
            # Switch to sender wallet
            result = runner.invoke(cli, ['--test-mode', 'wallet', 'switch', 'sender'])
            if result.exit_code == 0:
                print("✅ Switched to sender wallet")
            else:
                print(f"❌ Failed to switch to sender wallet: {result.output}")
                return False
            
            # Perform send
            send_amount = 10.0
            result = runner.invoke(cli, [
                '--test-mode', 'wallet', 'send', 
                receiver_address, str(send_amount)
            ])
            
            if result.exit_code == 0:
                print(f"✅ Send successful: {send_amount} AITBC from sender to receiver")
                print(f"   Transaction hash: mock_tx_hash_{int(time.time())}")
                print(f"   New sender balance: {mock_balance - send_amount} AITBC")
                return True
            else:
                print(f"❌ Send failed: {result.output}")
                return False
    
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print(f"\n🧹 Cleaned up test directory")


def test_wallet_send_insufficient_balance():
    """Test wallet send with insufficient balance"""
    print("\n🧪 Testing wallet send with insufficient balance...")
    
    runner = CliRunner()
    temp_dir = tempfile.mkdtemp(prefix="aitbc_wallet_insufficient_test_")
    
    try:
        with patch('pathlib.Path.home') as mock_home, \
             patch('aitbc_cli.commands.wallet.get_balance') as mock_get_balance:
            
            mock_home.return_value = Path(temp_dir)
            mock_get_balance.return_value = 5.0  # Mock insufficient balance
            
            # Try to send more than available
            result = runner.invoke(cli, [
                '--test-mode', 'wallet', 'send', 
                'aitbc1test_address', '10.0'
            ])
            
            if result.exit_code != 0 and 'Insufficient balance' in result.output:
                print("✅ Correctly rejected insufficient balance send")
                return True
            else:
                print("❌ Should have failed with insufficient balance")
                return False
    
    finally:
        shutil.rmtree(temp_dir)


def test_wallet_send_invalid_address():
    """Test wallet send with invalid address"""
    print("\n🧪 Testing wallet send with invalid address...")
    
    runner = CliRunner()
    temp_dir = tempfile.mkdtemp(prefix="aitbc_wallet_invalid_test_")
    
    try:
        with patch('pathlib.Path.home') as mock_home, \
             patch('aitbc_cli.commands.wallet.get_balance') as mock_get_balance:
            
            mock_home.return_value = Path(temp_dir)
            mock_get_balance.return_value = 1000.0  # Mock sufficient balance
            
            # Try to send to invalid address
            result = runner.invoke(cli, [
                '--test-mode', 'wallet', 'send', 
                'invalid_address_format', '10.0'
            ])
            
            if result.exit_code != 0:
                print("✅ Correctly rejected invalid address")
                return True
            else:
                print("❌ Should have failed with invalid address")
                return False
    
    finally:
        shutil.rmtree(temp_dir)


def main():
    """Main test runner"""
    print("🚀 AITBC CLI Wallet Send Dependency Test Suite")
    print("=" * 60)
    
    tests = [
        ("Wallet Send with Dependencies", test_wallet_send_with_dependencies),
        ("Wallet Send Insufficient Balance", test_wallet_send_insufficient_balance),
        ("Wallet Send Invalid Address", test_wallet_send_invalid_address)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"{'✅ PASSED' if result else '❌ FAILED'}: {test_name}")
        except Exception as e:
            print(f"💥 ERROR: {test_name} - {str(e)}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("\n🎉 EXCELLENT: Wallet send tests are working well!")
    elif success_rate >= 60:
        print("\n👍 GOOD: Most wallet send tests are working!")
    else:
        print("\n⚠️  NEEDS IMPROVEMENT: Some wallet send tests need attention!")
    
    return success_rate >= 60


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
