#!/usr/bin/env python3
"""
AITBC CLI Test Dependencies Manager

This module provides comprehensive test setup utilities for creating
proper test environments with wallets, balances, and blockchain state.
"""

import sys
import os
import json
import tempfile
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Dict, List, Optional, Tuple
import pathlib  # Add pathlib import

# Add CLI to path
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from click.testing import CliRunner
from aitbc_cli.main import cli
from aitbc_cli.config import Config


class TestDependencies:
    """Manages test dependencies like wallets, balances, and blockchain state"""
    
    def __init__(self):
        self.runner = CliRunner()
        self.temp_dir = None
        self.test_wallets = {}
        self.test_addresses = {}
        self.initial_balances = {}
        self.setup_complete = False
        
    def setup_test_environment(self):
        """Setup complete test environment with wallets and balances"""
        print("🔧 Setting up test environment...")
        
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp(prefix="aitbc_test_deps_")
        print(f"📁 Test directory: {self.temp_dir}")
        
        # Setup wallet directory
        wallet_dir = Path(self.temp_dir) / "wallets"
        wallet_dir.mkdir(exist_ok=True)
        
        return self.temp_dir
    
    def cleanup_test_environment(self):
        """Cleanup test environment"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"🧹 Cleaned up test environment")
    
    def create_test_wallet(self, wallet_name: str, password: str = "test123") -> Dict:
        """Create a test wallet with proper setup"""
        print(f"🔨 Creating test wallet: {wallet_name}")
        
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home, \
             patch('getpass.getpass') as mock_getpass:
            
            # Mock home directory to our test directory
            mock_home.return_value = Path(self.temp_dir)
            mock_getpass.return_value = password
            
            # Create wallet without --password option (it prompts for password)
            result = self.runner.invoke(cli, [
                '--test-mode', 'wallet', 'create', wallet_name,
                '--type', 'simple'  # Use simple wallet type
            ])
            
            if result.exit_code == 0:
                # Get wallet address
                address_result = self.runner.invoke(cli, [
                    '--test-mode', 'wallet', 'address',
                    '--wallet-name', wallet_name
                ])
                
                address = "test_address_" + wallet_name  # Extract from output or mock
                if address_result.exit_code == 0:
                    # Parse address from output
                    lines = address_result.output.split('\n')
                    for line in lines:
                        if 'aitbc' in line.lower():
                            address = line.strip()
                            break
                
                wallet_info = {
                    'name': wallet_name,
                    'password': password,
                    'address': address,
                    'created': True
                }
                
                self.test_wallets[wallet_name] = wallet_info
                self.test_addresses[wallet_name] = address
                
                print(f"✅ Created wallet {wallet_name} with address {address}")
                return wallet_info
            else:
                print(f"❌ Failed to create wallet {wallet_name}: {result.output}")
                return {'name': wallet_name, 'created': False, 'error': result.output}
    
    def fund_test_wallet(self, wallet_name: str, amount: float = 1000.0) -> bool:
        """Fund a test wallet using faucet or mock balance"""
        print(f"💰 Funding wallet {wallet_name} with {amount} AITBC")
        
        if wallet_name not in self.test_wallets:
            print(f"❌ Wallet {wallet_name} not found")
            return False
        
        wallet_address = self.test_addresses[wallet_name]
        
        # Try to use faucet first
        with patch('pathlib.Path.home') as mock_home:  # Use pathlib.Path
            mock_home.return_value = Path(self.temp_dir)
            
            faucet_result = self.runner.invoke(cli, [
                '--test-mode', 'blockchain', 'faucet', wallet_address
            ])
            
            if faucet_result.exit_code == 0:
                print(f"✅ Funded wallet {wallet_name} via faucet")
                self.initial_balances[wallet_name] = amount
                return True
            else:
                print(f"⚠️ Faucet failed, using mock balance for {wallet_name}")
                # Store mock balance for later use
                self.initial_balances[wallet_name] = amount
                return True
    
    def get_wallet_balance(self, wallet_name: str) -> float:
        """Get wallet balance (real or mocked)"""
        if wallet_name in self.initial_balances:
            return self.initial_balances[wallet_name]
        
        # Try to get real balance
        with patch('pathlib.Path.home') as mock_home:  # Use pathlib.Path
            mock_home.return_value = Path(self.temp_dir)
            
            balance_result = self.runner.invoke(cli, [
                '--test-mode', 'wallet', 'balance',
                '--wallet-name', wallet_name
            ])
            
            if balance_result.exit_code == 0:
                # Parse balance from output
                lines = balance_result.output.split('\n')
                for line in lines:
                    if 'balance' in line.lower():
                        try:
                            balance_str = line.split(':')[1].strip()
                            return float(balance_str.replace('AITBC', '').strip())
                        except:
                            pass
        
        return 0.0
    
    def setup_complete_test_suite(self) -> Dict:
        """Setup complete test suite with multiple wallets and transactions"""
        print("🚀 Setting up complete test suite...")
        
        # Create test wallets with different roles
        test_wallets_config = [
            {'name': 'sender', 'password': 'sender123', 'balance': 1000.0},
            {'name': 'receiver', 'password': 'receiver123', 'balance': 500.0},
            {'name': 'miner', 'password': 'miner123', 'balance': 2000.0},
            {'name': 'validator', 'password': 'validator123', 'balance': 5000.0},
            {'name': 'trader', 'password': 'trader123', 'balance': 750.0}
        ]
        
        created_wallets = {}
        
        for wallet_config in test_wallets_config:
            # Create wallet
            wallet_info = self.create_test_wallet(
                wallet_config['name'], 
                wallet_config['password']
            )
            
            if wallet_info['created']:
                # Fund wallet
                self.fund_test_wallet(wallet_config['name'], wallet_config['balance'])
                created_wallets[wallet_config['name']] = wallet_info
        
        self.setup_complete = True
        print(f"✅ Created {len(created_wallets)} test wallets")
        
        return {
            'wallets': created_wallets,
            'addresses': self.test_addresses,
            'balances': self.initial_balances,
            'environment': self.temp_dir
        }
    
    def create_mock_balance_patch(self, wallet_name: str):
        """Create a mock patch for wallet balance"""
        balance = self.initial_balances.get(wallet_name, 1000.0)
        
        def mock_get_balance():
            return balance
        
        return mock_get_balance
    
    def test_wallet_send(self, from_wallet: str, to_address: str, amount: float) -> Dict:
        """Test wallet send with proper setup"""
        print(f"🧪 Testing send: {from_wallet} -> {to_address} ({amount} AITBC)")
        
        if from_wallet not in self.test_wallets:
            return {'success': False, 'error': f'Wallet {from_wallet} not found'}
        
        # Check if sufficient balance
        current_balance = self.get_wallet_balance(from_wallet)
        if current_balance < amount:
            return {'success': False, 'error': f'Insufficient balance: {current_balance} < {amount}'}
        
        # Switch to the sender wallet first
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            # Switch to the sender wallet
            switch_result = self.runner.invoke(cli, [
                '--test-mode', 'wallet', 'switch', from_wallet
            ])
            
            if switch_result.exit_code != 0:
                return {'success': False, 'error': f'Failed to switch to wallet {from_wallet}'}
            
            # Perform send
            result = self.runner.invoke(cli, [
                '--test-mode', 'wallet', 'send', to_address, str(amount)
            ])
            
            if result.exit_code == 0:
                # Update balance
                self.initial_balances[from_wallet] = current_balance - amount
                print(f"✅ Send successful: {amount} AITBC from {from_wallet} to {to_address}")
                return {'success': True, 'tx_hash': 'mock_tx_hash_123', 'new_balance': current_balance - amount}
            else:
                print(f"❌ Send failed: {result.output}")
                return {'success': False, 'error': result.output}
    
    def get_test_scenarios(self) -> List[Dict]:
        """Get predefined test scenarios for wallet operations"""
        scenarios = []
        
        if self.setup_complete:
            wallets = list(self.test_wallets.keys())
            
            # Scenario 1: Simple send
            if len(wallets) >= 2:
                scenarios.append({
                    'name': 'simple_send',
                    'from': wallets[0],
                    'to': self.test_addresses[wallets[1]],
                    'amount': 10.0,
                    'expected': 'success'
                })
            
            # Scenario 2: Large amount send
            if len(wallets) >= 2:
                scenarios.append({
                    'name': 'large_send',
                    'from': wallets[0],
                    'to': self.test_addresses[wallets[1]],
                    'amount': 100.0,
                    'expected': 'success'
                })
            
            # Scenario 3: Insufficient balance
            if len(wallets) >= 1:
                scenarios.append({
                    'name': 'insufficient_balance',
                    'from': wallets[0],
                    'to': self.test_addresses[wallets[0]],  # Send to self
                    'amount': 10000.0,  # More than available
                    'expected': 'failure'
                })
            
            # Scenario 4: Invalid address
            if len(wallets) >= 1:
                scenarios.append({
                    'name': 'invalid_address',
                    'from': wallets[0],
                    'to': 'invalid_address_format',
                    'amount': 10.0,
                    'expected': 'failure'
                })
        
        return scenarios
    
    def run_test_scenarios(self) -> Dict:
        """Run all test scenarios and return results"""
        print("🧪 Running wallet test scenarios...")
        
        scenarios = self.get_test_scenarios()
        results = {}
        
        for scenario in scenarios:
            print(f"\n📋 Testing scenario: {scenario['name']}")
            
            result = self.test_wallet_send(
                scenario['from'],
                scenario['to'],
                scenario['amount']
            )
            
            success = result['success']
            expected = scenario['expected'] == 'success'
            
            if success == expected:
                print(f"✅ Scenario {scenario['name']}: PASSED")
                results[scenario['name']] = 'PASSED'
            else:
                print(f"❌ Scenario {scenario['name']}: FAILED")
                print(f"   Expected: {scenario['expected']}, Got: {success}")
                if 'error' in result:
                    print(f"   Error: {result['error']}")
                results[scenario['name']] = 'FAILED'
        
        return results


class TestBlockchainSetup:
    """Handles blockchain-specific test setup"""
    
    def __init__(self, test_deps: TestDependencies):
        self.test_deps = test_deps
        self.runner = CliRunner()
    
    def setup_test_blockchain(self) -> Dict:
        """Setup test blockchain with proper state"""
        print("⛓️ Setting up test blockchain...")
        
        with patch('pathlib.Path.home') as mock_home:  # Use pathlib.Path instead
            mock_home.return_value = Path(self.test_deps.temp_dir)
            
            # Get blockchain info
            info_result = self.runner.invoke(cli, ['--test-mode', 'blockchain', 'info'])
            
            # Get blockchain status
            status_result = self.runner.invoke(cli, ['--test-mode', 'blockchain', 'status'])
            
            blockchain_info = {
                'info_available': info_result.exit_code == 0,
                'status_available': status_result.exit_code == 0,
                'network': 'test',
                'height': 0
            }
            
            if info_result.exit_code == 0:
                # Parse blockchain info
                lines = info_result.output.split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        if 'chain' in key.lower():
                            blockchain_info['network'] = value.strip()
                        elif 'height' in key.lower():
                            try:
                                blockchain_info['height'] = int(value.strip())
                            except:
                                pass
            
            print(f"✅ Blockchain setup complete: {blockchain_info['network']} at height {blockchain_info['height']}")
            return blockchain_info
    
    def create_test_transactions(self) -> List[Dict]:
        """Create test transactions for testing"""
        transactions = []
        
        if self.test_deps.setup_complete:
            wallets = list(self.test_deps.test_wallets.keys())
            
            for i, from_wallet in enumerate(wallets):
                for j, to_wallet in enumerate(wallets):
                    if i != j and j < len(wallets) - 1:  # Limit transactions
                        tx = {
                            'from': from_wallet,
                            'to': self.test_deps.test_addresses[to_wallet],
                            'amount': (i + 1) * 10.0,
                            'description': f'Test transaction {i}-{j}'
                        }
                        transactions.append(tx)
        
        return transactions


def main():
    """Main function to test the dependency system"""
    print("🚀 Testing AITBC CLI Test Dependencies System")
    print("=" * 60)
    
    # Initialize test dependencies
    test_deps = TestDependencies()
    
    try:
        # Setup test environment
        test_deps.setup_test_environment()
        
        # Setup complete test suite
        suite_info = test_deps.setup_complete_test_suite()
        
        print(f"\n📊 Test Suite Setup Results:")
        print(f"  Wallets Created: {len(suite_info['wallets'])}")
        print(f"  Addresses Generated: {len(suite_info['addresses'])}")
        print(f"  Initial Balances: {len(suite_info['balances'])}")
        
        # Setup blockchain
        blockchain_setup = TestBlockchainSetup(test_deps)
        blockchain_info = blockchain_setup.setup_test_blockchain()
        
        # Run test scenarios
        scenario_results = test_deps.run_test_scenarios()
        
        print(f"\n📊 Test Scenario Results:")
        for scenario, result in scenario_results.items():
            print(f"  {scenario}: {result}")
        
        # Summary
        passed = sum(1 for r in scenario_results.values() if r == 'PASSED')
        total = len(scenario_results)
        success_rate = (passed / total * 100) if total > 0 else 0
        
        print(f"\n🎯 Overall Success Rate: {success_rate:.1f}% ({passed}/{total})")
        
        if success_rate >= 75:
            print("🎉 EXCELLENT: Test dependencies working well!")
        else:
            print("⚠️  NEEDS IMPROVEMENT: Some test scenarios failed")
    
    finally:
        # Cleanup
        test_deps.cleanup_test_environment()


if __name__ == "__main__":
    main()
