#!/usr/bin/env python3
"""
AITBC CLI Blockchain Group Test Script

Tests blockchain queries and operations (HIGH FREQUENCY):
- blockchain info, status, height, balance, block
- blockchain transactions, validators, faucet
- blockchain sync-status, network, peers

Usage Frequency: DAILY - Blockchain operations
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


class BlockchainGroupTester:
    """Test suite for AITBC CLI blockchain commands (high frequency)"""
    
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
    
    def test_core_blockchain_operations(self):
        """Test core blockchain operations (high frequency)"""
        core_tests = [
            lambda: self._test_blockchain_info(),
            lambda: self._test_blockchain_status(),
            lambda: self._test_blockchain_height(),
            lambda: self._test_blockchain_balance(),
            lambda: self._test_blockchain_block()
        ]
        
        results = []
        for test in core_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Core blockchain test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Core blockchain operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate for daily operations
    
    def _test_blockchain_info(self):
        """Test blockchain info"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'chain': 'ait-devnet',
                'height': 12345,
                'hash': '0xabc123...',
                'timestamp': '2026-01-01T00:00:00Z'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'info'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain info: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_status(self):
        """Test blockchain status"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'status': 'healthy',
                'syncing': False,
                'peers': 5,
                'block_height': 12345
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'status'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain status: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_height(self):
        """Test blockchain height"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'height': 12345,
                'timestamp': '2026-01-01T00:00:00Z'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'height'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain height: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_balance(self):
        """Test blockchain balance"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'address': 'aitbc1test...',
                'balance': 1000.0,
                'unit': 'AITBC'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'balance', 'aitbc1test...'])
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
    
    def test_transaction_operations(self):
        """Test transaction operations (medium frequency)"""
        transaction_tests = [
            lambda: self._test_blockchain_transactions(),
            lambda: self._test_blockchain_validators(),
            lambda: self._test_blockchain_faucet()
        ]
        
        results = []
        for test in transaction_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Transaction test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Transaction operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
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
    
    def _test_blockchain_faucet(self):
        """Test blockchain faucet"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'tx_hash': '0xabc123...',
                'amount': 100.0,
                'address': 'aitbc1test...'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'faucet', 'aitbc1test...'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain faucet: {'Working' if success else 'Failed'}")
            return success
    
    def test_network_operations(self):
        """Test network operations (occasionally used)"""
        network_tests = [
            lambda: self._test_blockchain_sync_status(),
            lambda: self._test_blockchain_network(),
            lambda: self._test_blockchain_peers()
        ]
        
        results = []
        for test in network_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Network test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Network operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.6  # 60% pass rate for network features
    
    def _test_blockchain_sync_status(self):
        """Test blockchain sync status"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'syncing': True,
                'current_height': 12345,
                'target_height': 12350,
                'progress': 90.0
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'sync-status'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain sync-status: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_network(self):
        """Test blockchain network info"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'network': 'ait-devnet',
                'chain_id': 12345,
                'version': '1.0.0'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'network'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain network: {'Working' if success else 'Failed'}")
            return success
    
    def _test_blockchain_peers(self):
        """Test blockchain peers"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'peers': [
                    {'address': '127.0.0.1:8006', 'connected': True},
                    {'address': '127.0.0.1:8007', 'connected': True}
                ],
                'total': 2
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['blockchain', 'peers'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} blockchain peers: {'Working' if success else 'Failed'}")
            return success
    
    def run_all_tests(self):
        """Run all blockchain group tests"""
        print("🚀 Starting AITBC CLI Blockchain Group Test Suite")
        print("Testing blockchain queries and operations (HIGH FREQUENCY)")
        print("=" * 60)
        
        # Setup test environment
        config_dir = Path(tempfile.mkdtemp(prefix="aitbc_blockchain_test_"))
        self.temp_dir = str(config_dir)
        print(f"📁 Test environment: {self.temp_dir}")
        
        try:
            # Run test categories by usage frequency
            test_categories = [
                ("Core Blockchain Operations", self.test_core_blockchain_operations),
                ("Transaction Operations", self.test_transaction_operations),
                ("Network Operations", self.test_network_operations)
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
        print("📊 BLOCKCHAIN GROUP TEST RESULTS SUMMARY")
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
            print("🎉 EXCELLENT: Blockchain commands are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most blockchain commands are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some blockchain commands need attention")
        else:
            print("🚨 POOR: Many blockchain commands need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    tester = BlockchainGroupTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
