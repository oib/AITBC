#!/usr/bin/env python3
"""
AITBC CLI Level 2 Commands Test Script

Tests essential subcommands and their core functionality:
- Most commonly used operations (50-60 commands)
- Core workflows for daily use
- Essential wallet, client, miner operations
- Basic blockchain and marketplace operations

Level 2 Commands: Essential subcommands for daily operations
"""

import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add CLI to path
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from click.testing import CliRunner
from aitbc_cli.main import cli
from aitbc_cli.config import Config

# Import test utilities
try:
    from utils.test_helpers import TestEnvironment, mock_api_responses
    from utils.command_tester import CommandTester
except ImportError:
    # Fallback if utils not in path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from utils.test_helpers import TestEnvironment, mock_api_responses
    from utils.command_tester import CommandTester


class Level2CommandTester:
    """Test suite for AITBC CLI Level 2 commands (essential subcommands)"""
    
    def __init__(self):
        self.runner = CliRunner()
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'tests': []
        }
        self.temp_dir = None
        
    def cleanup(self):
        """Cleanup test environment"""
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
    
    def test_wallet_subcommands(self):
        """Test essential wallet subcommands"""
        wallet_tests = [
            # Core wallet operations
            lambda: self._test_wallet_create(),
            lambda: self._test_wallet_list(),
            lambda: self._test_wallet_balance(),
            lambda: self._test_wallet_address(),
            lambda: self._test_wallet_send(),
            # Transaction operations
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
        print(f"  Wallet subcommands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_wallet_create(self):
        """Test wallet creation"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home, \
             patch('getpass.getpass') as mock_getpass:
            
            mock_home.return_value = Path(self.temp_dir)
            mock_getpass.return_value = 'test-password'
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'create', 'level2-test-wallet'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet create: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_list(self):
        """Test wallet listing"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'list'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet list: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_balance(self):
        """Test wallet balance check"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home, \
             patch('httpx.get') as mock_get:
            
            mock_home.return_value = Path(self.temp_dir)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'address': 'test-address',
                'balance': 1000.0,
                'unlocked': 800.0,
                'staked': 200.0
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'balance'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet balance: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_address(self):
        """Test wallet address display"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'address'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet address: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_send(self):
        """Test wallet send operation"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home, \
             patch('httpx.post') as mock_post:
            
            mock_home.return_value = Path(self.temp_dir)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'tx_hash': '0x1234567890abcdef',
                'status': 'success'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'send', 'test-address', '10.0'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet send: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_history(self):
        """Test wallet transaction history"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home, \
             patch('httpx.get') as mock_get:
            
            mock_home.return_value = Path(self.temp_dir)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'transactions': [
                    {'hash': '0x123', 'type': 'send', 'amount': 10.0},
                    {'hash': '0x456', 'type': 'receive', 'amount': 5.0}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'history', '--limit', '5'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet history: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_backup(self):
        """Test wallet backup"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home, \
             patch('shutil.copy2') as mock_copy:
            
            mock_home.return_value = Path(self.temp_dir)
            mock_copy.return_value = True
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'backup', 'test-wallet'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet backup: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_info(self):
        """Test wallet info display"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'info'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet info: {'Working' if success else 'Failed'}")
            return success
    
    def test_client_subcommands(self):
        """Test essential client subcommands"""
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
        print(f"  Client subcommands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_client_submit(self):
        """Test job submission"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_level2_test123',
                'status': 'pending',
                'submitted_at': '2026-01-01T00:00:00Z'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'client', 'submit', 'What is machine learning?', '--model', 'gemma3:1b'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client submit: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_status(self):
        """Test job status check"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_level2_test123',
                'status': 'completed',
                'progress': 100
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'client', 'status', 'job_level2_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client status: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_result(self):
        """Test job result retrieval"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_level2_test123',
                'status': 'completed',
                'result': 'Machine learning is a subset of artificial intelligence...',
                'completed_at': '2026-01-01T00:05:00Z'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'client', 'result', 'job_level2_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client result: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_history(self):
        """Test job history"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'jobs': [
                    {'job_id': 'job1', 'status': 'completed', 'model': 'gemma3:1b'},
                    {'job_id': 'job2', 'status': 'pending', 'model': 'llama3.2:latest'}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'client', 'history', '--limit', '5'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client history: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_cancel(self):
        """Test job cancellation"""
        with patch('httpx.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_level2_test123',
                'status': 'cancelled',
                'cancelled_at': '2026-01-01T00:03:00Z'
            }
            mock_delete.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'client', 'cancel', 'job_level2_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client cancel: {'Working' if success else 'Failed'}")
            return success
    
    def test_miner_subcommands(self):
        """Test essential miner subcommands"""
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
        print(f"  Miner subcommands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_miner_register(self):
        """Test miner registration"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'miner_id': 'miner_level2_test',
                'status': 'registered',
                'registered_at': '2026-01-01T00:00:00Z'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'miner', 'register'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner register: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_status(self):
        """Test miner status check"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'miner_id': 'miner_level2_test',
                'status': 'active',
                'current_jobs': 1,
                'total_jobs_completed': 25
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'miner', 'status'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner status: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_earnings(self):
        """Test miner earnings check"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'total_earnings': 100.0,
                'today_earnings': 5.0,
                'jobs_completed': 25,
                'average_per_job': 4.0
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'miner', 'earnings'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner earnings: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_jobs(self):
        """Test miner jobs list"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'current_jobs': [
                    {'job_id': 'job1', 'status': 'running', 'progress': 75},
                    {'job_id': 'job2', 'status': 'completed', 'progress': 100}
                ],
                'completed_jobs': [
                    {'job_id': 'job3', 'status': 'completed', 'earnings': 4.0}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'miner', 'jobs'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner jobs: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_deregister(self):
        """Test miner deregistration"""
        with patch('httpx.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'miner_id': 'miner_level2_test',
                'status': 'deregistered',
                'deregistered_at': '2026-01-01T00:00:00Z'
            }
            mock_delete.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'miner', 'deregister'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner deregister: {'Working' if success else 'Failed'}")
            return success
    
    def test_blockchain_subcommands(self):
        """Test essential blockchain subcommands"""
        blockchain_tests = [
            lambda: self._test_blockchain_balance(),
            lambda: self._test_blockchain_block(),
            lambda: self._test_blockchain_height(),
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
        print(f"  Blockchain subcommands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_blockchain_balance(self):
        """Test blockchain balance query"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'address': 'test-address',
                'balance': 1000.0,
                'unlocked': 800.0,
                'staked': 200.0
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'blockchain', 'balance', 'test-address'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain balance: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_block(self):
        """Test blockchain block query"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'height': 1000,
                'hash': '0x1234567890abcdef',
                'timestamp': '2026-01-01T00:00:00Z',
                'num_txs': 5
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'blockchain', 'block', '1000'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain block: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_height(self):
        """Test blockchain height query"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'height': 1000,
                'timestamp': '2026-01-01T00:00:00Z'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'blockchain', 'height'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain height: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_transactions(self):
        """Test blockchain transactions query"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'transactions': [
                    {'hash': '0x123', 'from': 'addr1', 'to': 'addr2', 'amount': 10.0},
                    {'hash': '0x456', 'from': 'addr2', 'to': 'addr3', 'amount': 5.0}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'blockchain', 'transactions', '--limit', '5'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain transactions: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_validators(self):
        """Test blockchain validators query"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'validators': [
                    {'address': 'val1', 'stake': 1000.0, 'status': 'active'},
                    {'address': 'val2', 'stake': 800.0, 'status': 'active'}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'blockchain', 'validators'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain validators: {'Working' if success else 'Failed'}")
            return success
    
    def test_marketplace_subcommands(self):
        """Test essential marketplace subcommands"""
        marketplace_tests = [
            lambda: self._test_marketplace_list(),
            lambda: self._test_marketplace_register(),
            lambda: self._test_marketplace_bid(),
            lambda: self._test_marketplace_orders()
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
        print(f"  Marketplace subcommands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate
    
    def _test_marketplace_list(self):
        """Test marketplace GPU listing"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'gpus': [
                    {'id': 'gpu1', 'name': 'RTX 4090', 'price': 0.50, 'status': 'available'},
                    {'id': 'gpu2', 'name': 'A100', 'price': 1.00, 'status': 'busy'}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'marketplace', 'gpu', 'list'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace list: {'Working' if success else 'Failed'}")
            return success
    
    def _test_marketplace_register(self):
        """Test marketplace GPU registration"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'gpu_id': 'gpu_level2_test',
                'status': 'registered',
                'price_per_hour': 0.75
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'marketplace', 'gpu', 'register', '--name', 'RTX-4090', '--price-per-hour', '0.75'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace register: {'Working' if success else 'Failed'}")
            return success
    
    def _test_marketplace_bid(self):
        """Test marketplace bid placement"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'bid_id': 'bid_level2_test',
                'gpu_id': 'gpu1',
                'amount': 0.45,
                'status': 'placed'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'marketplace', 'bid', 'submit', '--provider', 'gpu1', '--capacity', '1', '--price', '0.45'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace bid: {'Working' if success else 'Failed'}")
            return success
    
    def _test_marketplace_orders(self):
        """Test marketplace orders listing"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'total_gpus': 100,
                'available_gpus': 45,
                'active_bids': 12,
                'average_price': 0.65
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['--test-mode', 'marketplace', 'orders'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} marketplace orders: {'Working' if success else 'Failed'}")
            return success
    
    def run_all_tests(self):
        """Run all Level 2 command tests"""
        print("🚀 Starting AITBC CLI Level 2 Commands Test Suite")
        print("Testing essential subcommands for daily operations")
        print("=" * 60)
        
        # Setup test environment
        config_dir = Path(tempfile.mkdtemp(prefix="aitbc_level2_test_"))
        self.temp_dir = str(config_dir)
        print(f"📁 Test environment: {self.temp_dir}")
        
        try:
            # Run test categories
            test_categories = [
                ("Wallet Subcommands", self.test_wallet_subcommands),
                ("Client Subcommands", self.test_client_subcommands),
                ("Miner Subcommands", self.test_miner_subcommands),
                ("Blockchain Subcommands", self.test_blockchain_subcommands),
                ("Marketplace Subcommands", self.test_marketplace_subcommands)
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
    
    def print_results(self):
        """Print test results summary"""
        print("\n" + "=" * 60)
        print("📊 LEVEL 2 TEST RESULTS SUMMARY")
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
            print("🎉 EXCELLENT: Level 2 commands are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most Level 2 commands are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some Level 2 commands need attention")
        else:
            print("🚨 POOR: Many Level 2 commands need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    tester = Level2CommandTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
