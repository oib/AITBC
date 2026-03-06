#!/usr/bin/env python3
"""
AITBC CLI Level 2 Commands Test with Dependencies

Tests essential subcommands with proper test dependencies including:
- Wallet operations with actual balances
- Client operations with test jobs
- Miner operations with test miners
- Blockchain operations with test state
- Marketplace operations with test GPU listings

Level 2 Commands: Essential subcommands with real dependencies
"""

import sys
import os
import json
import tempfile
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add CLI to path
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from click.testing import CliRunner
from aitbc_cli.main import cli
from aitbc_cli.config import Config

# Import test dependencies
try:
    from test_dependencies import TestDependencies, TestBlockchainSetup
except ImportError:
    # Fallback if in different directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_dependencies import TestDependencies, TestBlockchainSetup


class Level2WithDependenciesTester:
    """Test suite for AITBC CLI Level 2 commands with proper dependencies"""
    
    def __init__(self):
        self.runner = CliRunner()
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'tests': []
        }
        self.temp_dir = None
        self.test_deps = None
        self.blockchain_setup = None
        
    def cleanup(self):
        """Cleanup test environment"""
        if self.test_deps:
            self.test_deps.cleanup_test_environment()
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"🧹 Cleaned up test environment")
    
    def run_test(self, test_name, test_func):
        """Run a single test and track results"""
        print(f"\n🧪 Running: {test_name}")
        try:
            result = test_func()
            if result:
                print(f"✅ PASSED: {test_name}")
                self.test_results['passed'] += 1
                self.test_results['tests'].append({'name': test_name, 'status': 'PASSED'})
            else:
                print(f"❌ FAILED: {test_name}")
                self.test_results['failed'] += 1
                self.test_results['tests'].append({'name': test_name, 'status': 'FAILED'})
        except Exception as e:
            print(f"💥 ERROR: {test_name} - {str(e)}")
            self.test_results['failed'] += 1
            self.test_results['tests'].append({'name': test_name, 'status': 'ERROR', 'error': str(e)})
    
    def setup_dependencies(self):
        """Setup all test dependencies"""
        print("🔧 Setting up test dependencies...")
        
        # Initialize test dependencies
        self.test_deps = TestDependencies()
        self.temp_dir = self.test_deps.setup_test_environment()
        
        # Setup complete test suite with wallets
        suite_info = self.test_deps.setup_complete_test_suite()
        
        # Setup blockchain
        self.blockchain_setup = TestBlockchainSetup(self.test_deps)
        blockchain_info = self.blockchain_setup.setup_test_blockchain()
        
        print(f"✅ Dependencies setup complete")
        print(f"  Wallets: {len(suite_info['wallets'])}")
        print(f"  Blockchain: {blockchain_info['network']}")
        
        return suite_info, blockchain_info
    
    def test_wallet_operations_with_balance(self):
        """Test wallet operations with actual balances"""
        if not self.test_deps or not self.test_deps.setup_complete:
            print("  ❌ Test dependencies not setup")
            return False
        
        wallet_tests = [
            lambda: self._test_wallet_create(),
            lambda: self._test_wallet_list(),
            lambda: self._test_wallet_balance(),
            lambda: self._test_wallet_address(),
            lambda: self._test_wallet_send_with_balance(),
            lambda: self._test_wallet_history(),
            lambda: self._test_wallet_backup(),
            lambda: self._test_wallet_info()
        ]
        
        results = []
        for test in wallet_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Wallet test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Wallet operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_wallet_create(self):
        """Test wallet creation"""
        # Create a new test wallet
        wallet_name = f"test_wallet_{int(time.time())}"
        wallet_info = self.test_deps.create_test_wallet(wallet_name, "test123")
        
        success = wallet_info['created']
        print(f"    {'✅' if success else '❌'} wallet create: {'Working' if success else 'Failed'}")
        return success
    
    def _test_wallet_list(self):
        """Test wallet listing"""
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'list'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet list: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_balance(self):
        """Test wallet balance check"""
        if not self.test_deps.test_wallets:
            return False
        
        wallet_name = list(self.test_deps.test_wallets.keys())[0]
        balance = self.test_deps.get_wallet_balance(wallet_name)
        
        success = balance >= 0
        print(f"    {'✅' if success else '❌'} wallet balance: {balance} AITBC")
        return success
    
    def _test_wallet_address(self):
        """Test wallet address display"""
        if not self.test_deps.test_wallets:
            return False
        
        wallet_name = list(self.test_deps.test_wallets.keys())[0]
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'address', '--wallet-name', wallet_name])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet address: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_send_with_balance(self):
        """Test wallet send with actual balance"""
        if not self.test_deps.setup_complete:
            return False
        
        wallets = list(self.test_deps.test_wallets.keys())
        if len(wallets) < 2:
            return False
        
        from_wallet = wallets[0]
        to_address = self.test_deps.test_addresses[wallets[1]]
        amount = 10.0
        
        # Check if sufficient balance
        current_balance = self.test_deps.get_wallet_balance(from_wallet)
        if current_balance < amount:
            print(f"    ⚠️ wallet send: Insufficient balance ({current_balance} < {amount})")
            return False
        
        # Perform send with proper mocking
        with patch('pathlib.Path.home') as mock_home, \
             patch('aitbc_cli.commands.wallet.get_balance') as mock_balance:
            
            mock_home.return_value = Path(self.temp_dir)
            mock_balance.return_value = current_balance  # Mock sufficient balance
            
            # Switch to the sender wallet first
            switch_result = self.runner.invoke(cli, [
                '--test-mode', 'wallet', 'switch', from_wallet
            ])
            
            if switch_result.exit_code != 0:
                print(f"    ❌ wallet send: Failed to switch to wallet {from_wallet}")
                return False
            
            # Perform send
            result = self.runner.invoke(cli, [
                '--test-mode', 'wallet', 'send', to_address, str(amount)
            ])
            
            success = result.exit_code == 0
            
            print(f"    {'✅' if success else '❌'} wallet send: {'Working' if success else 'Failed'}")
            if not success:
                print(f"      Error: {result.output}")
            
            return success
    
    def _test_wallet_history(self):
        """Test wallet transaction history"""
        if not self.test_deps.test_wallets:
            return False
        
        wallet_name = list(self.test_deps.test_wallets.keys())[0]
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'history', '--limit', '5', '--wallet-name', wallet_name])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet history: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_backup(self):
        """Test wallet backup"""
        if not self.test_deps.test_wallets:
            return False
        
        wallet_name = list(self.test_deps.test_wallets.keys())[0]
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'backup', wallet_name])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet backup: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_info(self):
        """Test wallet info"""
        if not self.test_deps.test_wallets:
            return False
        
        wallet_name = list(self.test_deps.test_wallets.keys())[0]
        
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'info', '--wallet-name', wallet_name])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet info: {'Working' if success else 'Failed'}")
            return success
    
    def test_client_operations_with_jobs(self):
        """Test client operations with test jobs"""
        client_tests = [
            lambda: self._test_client_submit(),
            lambda: self._test_client_status(),
            lambda: self._test_client_result(),
            lambda: self._test_client_history(),
            lambda: self._test_client_cancel()
        ]
        
        results = []
        for test in client_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Client test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Client operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_client_submit(self):
        """Test client job submission"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test_' + str(int(time.time())),
                'status': 'pending',
                'submitted_at': '2026-01-01T00:00:00Z'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'submit', 'What is machine learning?', '--model', 'gemma3:1b'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client submit: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_status(self):
        """Test client job status check"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test123',
                'status': 'completed',
                'progress': 100
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'status', 'job_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client status: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_result(self):
        """Test client job result retrieval"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test123',
                'result': 'Machine learning is a subset of AI...',
                'status': 'completed'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'result', 'job_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client result: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_history(self):
        """Test client job history"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'jobs': [
                    {'job_id': 'job1', 'status': 'completed'},
                    {'job_id': 'job2', 'status': 'pending'}
                ],
                'total': 2
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'history', '--limit', '10'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client history: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_cancel(self):
        """Test client job cancellation"""
        with patch('httpx.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test123',
                'status': 'cancelled'
            }
            mock_delete.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'cancel', 'job_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client cancel: {'Working' if success else 'Failed'}")
            return success
    
    def test_miner_operations_with_registration(self):
        """Test miner operations with test miner registration"""
        miner_tests = [
            lambda: self._test_miner_register(),
            lambda: self._test_miner_status(),
            lambda: self._test_miner_earnings(),
            lambda: self._test_miner_jobs(),
            lambda: self._test_miner_deregister()
        ]
        
        results = []
        for test in miner_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Miner test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Miner operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_miner_register(self):
        """Test miner registration"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'miner_id': 'miner_test_' + str(int(time.time())),
                'status': 'registered',
                'gpu_info': {'name': 'RTX 4090', 'memory': '24GB'}
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'register', '--gpu', 'RTX 4090'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner register: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_status(self):
        """Test miner status"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'miner_id': 'miner_test123',
                'status': 'active',
                'gpu_utilization': 85.0,
                'jobs_completed': 100
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'status'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner status: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_earnings(self):
        """Test miner earnings"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'total_earnings': 1000.0,
                'currency': 'AITBC',
                'daily_earnings': 50.0,
                'jobs_completed': 100
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'earnings'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner earnings: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_jobs(self):
        """Test miner jobs"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'active_jobs': [
                    {'job_id': 'job1', 'status': 'running', 'progress': 50},
                    {'job_id': 'job2', 'status': 'pending', 'progress': 0}
                ],
                'total_active': 2
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'jobs'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner jobs: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_deregister(self):
        """Test miner deregistration"""
        with patch('httpx.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'miner_id': 'miner_test123',
                'status': 'deregistered'
            }
            mock_delete.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'deregister'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner deregister: {'Working' if success else 'Failed'}")
            return success
    
    def test_blockchain_operations_with_state(self):
        """Test blockchain operations with test blockchain state"""
        blockchain_tests = [
            lambda: self._test_blockchain_balance(),
            lambda: self._test_blockchain_block(),
            lambda: self._test_blockchain_head(),
            lambda: self._test_blockchain_transactions(),
            lambda: self._test_blockchain_validators()
        ]
        
        results = []
        for test in blockchain_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Blockchain test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Blockchain operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_blockchain_balance(self):
        """Test blockchain balance"""
        if not self.test_deps.test_wallets:
            return False
        
        wallet_name = list(self.test_deps.test_wallets.keys())[0]
        address = self.test_deps.test_addresses[wallet_name]
        
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'address': address,
                'balance': self.test_deps.get_wallet_balance(wallet_name),
                'unit': 'AITBC'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'balance', address])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain balance: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_block(self):
        """Test blockchain block"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'hash': '0xabc123...',
                'height': 12345,
                'timestamp': '2026-01-01T00:00:00Z',
                'transactions': []
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'block', '12345'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain block: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_head(self):
        """Test blockchain head"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'hash': '0xhead123...',
                'height': 12345,
                'timestamp': '2026-01-01T00:00:00Z'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'head'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain head: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_transactions(self):
        """Test blockchain transactions"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'transactions': [
                    {'hash': '0x123...', 'from': 'aitbc1...', 'to': 'aitbc2...', 'amount': 100.0},
                    {'hash': '0x456...', 'from': 'aitbc2...', 'to': 'aitbc3...', 'amount': 50.0}
                ],
                'total': 2
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'transactions', '--limit', '10'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain transactions: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_validators(self):
        """Test blockchain validators"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'validators': [
                    {'address': 'aitbc1val1...', 'stake': 1000.0, 'status': 'active'},
                    {'address': 'aitbc1val2...', 'stake': 2000.0, 'status': 'active'}
                ],
                'total': 2
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'validators'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain validators: {'Working' if success else 'Failed'}")
            return success
    
    def test_marketplace_operations_with_gpus(self):
        """Test marketplace operations with test GPU listings"""
        marketplace_tests = [
            lambda: self._test_marketplace_gpu_list(),
            lambda: self._test_marketplace_gpu_register(),
            lambda: self._test_marketplace_bid(),
            lambda: self._test_marketplace_gpu_details()
        ]
        
        results = []
        for test in marketplace_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Marketplace test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Marketplace operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_marketplace_gpu_list(self):
        """Test marketplace GPU listing"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'gpus': [
                    {'id': 'gpu1', 'name': 'RTX 4090', 'memory': '24GB', 'price': 0.50},
                    {'id': 'gpu2', 'name': 'RTX 3090', 'memory': '24GB', 'price': 0.40}
                ],
                'total': 2
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['marketplace', 'gpu', 'list'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace gpu list: {'Working' if success else 'Failed'}")
            return success
    
    def _test_marketplace_gpu_register(self):
        """Test marketplace GPU registration"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'gpu_id': 'gpu_test_' + str(int(time.time())),
                'status': 'registered',
                'name': 'Test GPU'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['marketplace', 'gpu', 'register', '--name', 'Test GPU', '--memory', '24GB'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace gpu register: {'Working' if success else 'Failed'}")
            return success
    
    def _test_marketplace_bid(self):
        """Test marketplace bid"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'bid_id': 'bid_test_' + str(int(time.time())),
                'status': 'active',
                'amount': 0.50
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['marketplace', 'bid', 'gpu1', '--amount', '0.50'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace bid: {'Working' if success else 'Failed'}")
            return success
    
    def _test_marketplace_gpu_details(self):
        """Test marketplace GPU details"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'id': 'gpu1',
                'name': 'RTX 4090',
                'memory': '24GB',
                'price': 0.50,
                'status': 'available',
                'owner': 'provider1'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['marketplace', 'gpu', 'details', '--gpu-id', 'gpu1'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace gpu details: {'Working' if success else 'Failed'}")
            return success
    
    def run_all_tests(self):
        """Run all Level 2 tests with dependencies"""
        print("🚀 Starting AITBC CLI Level 2 Commands Test Suite (WITH DEPENDENCIES)")
        print("Testing essential subcommands with proper test dependencies")
        print("=" * 60)
        
        try:
            # Setup dependencies
            suite_info, blockchain_info = self.setup_dependencies()
            
            if not self.test_deps.setup_complete:
                print("❌ Failed to setup test dependencies")
                return False
            
            # Run test categories
            test_categories = [
                ("Wallet Operations with Balance", self.test_wallet_operations_with_balance),
                ("Client Operations with Jobs", self.test_client_operations_with_jobs),
                ("Miner Operations with Registration", self.test_miner_operations_with_registration),
                ("Blockchain Operations with State", self.test_blockchain_operations_with_state),
                ("Marketplace Operations with GPUs", self.test_marketplace_operations_with_gpus)
            ]
            
            for category_name, test_func in test_categories:
                print(f"\n📂 Testing {category_name}")
                print("-" * 40)
                self.run_test(category_name, test_func)
        
        finally:
            # Cleanup
            self.cleanup()
        
        # Print results
        self.print_results()
        
        return self.test_results['failed'] == 0
    
    def print_results(self):
        """Print test results summary"""
        print("\n" + "=" * 60)
        print("📊 LEVEL 2 WITH DEPENDENCIES TEST RESULTS SUMMARY")
        print("=" * 60)
        
        total = self.test_results['passed'] + self.test_results['failed'] + self.test_results['skipped']
        
        print(f"Total Test Categories: {total}")
        print(f"✅ Passed: {self.test_results['passed']}")
        print(f"❌ Failed: {self.test_results['failed']}")
        print(f"⏭️  Skipped: {self.test_results['skipped']}")
        
        if self.test_results['failed'] > 0:
            print(f"\n❌ Failed Tests:")
            for test in self.test_results['tests']:
                if test['status'] in ['FAILED', 'ERROR']:
                    print(f"  - {test['name']}")
                    if 'error' in test:
                        print(f"    Error: {test['error']}")
        
        success_rate = (self.test_results['passed'] / total * 100) if total > 0 else 0
        print(f"\n🎯 Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("🎉 EXCELLENT: Level 2 commands with dependencies are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most Level 2 commands with dependencies are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some Level 2 commands with dependencies need attention")
        else:
            print("🚨 POOR: Many Level 2 commands with dependencies need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    # Import time for unique identifiers
    import time
    
    tester = Level2WithDependenciesTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
