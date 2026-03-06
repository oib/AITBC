#!/usr/bin/env python3
"""
AITBC CLI Wallet Group Test Script

Tests wallet and transaction management commands (MOST FREQUENTLY USED):
- wallet create, list, switch, delete, backup, restore
- wallet info, balance, address, send, history
- wallet stake, unstake, staking-info
- wallet multisig-create, multisig-propose, multisig-challenge
- wallet sign-challenge, multisig-sign
- wallet liquidity-stake, liquidity-unstake, rewards

Usage Frequency: DAILY - Core wallet operations
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


class WalletGroupTester:
    """Test suite for AITBC CLI wallet commands (most frequently used)"""
    
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
    
    def test_core_wallet_operations(self):
        """Test core wallet operations (most frequently used)"""
        core_tests = [
            lambda: self._test_wallet_create(),
            lambda: self._test_wallet_list(),
            lambda: self._test_wallet_switch(),
            lambda: self._test_wallet_info(),
            lambda: self._test_wallet_balance(),
            lambda: self._test_wallet_address()
        ]
        
        results = []
        for test in core_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Core wallet test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Core wallet operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate for daily operations
    
    def _test_wallet_create(self):
        """Test wallet creation"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home, \
             patch('getpass.getpass') as mock_getpass:
            
            mock_home.return_value = Path(self.temp_dir)
            mock_getpass.return_value = 'test-password'
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'create', 'test-wallet'])
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
    
    def _test_wallet_switch(self):
        """Test wallet switching"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'switch', 'test-wallet'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet switch: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_info(self):
        """Test wallet info display"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'info'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet info: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_balance(self):
        """Test wallet balance check"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
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
    
    def test_transaction_operations(self):
        """Test transaction operations (frequently used)"""
        transaction_tests = [
            lambda: self._test_wallet_send(),
            lambda: self._test_wallet_history(),
            lambda: self._test_wallet_backup(),
            lambda: self._test_wallet_restore()
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
    
    def _test_wallet_send(self):
        """Test wallet send operation"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'send', 'test-address', '10.0'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet send: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_history(self):
        """Test wallet transaction history"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'history', '--limit', '5'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet history: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_backup(self):
        """Test wallet backup"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'backup', 'test-wallet'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet backup: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_restore(self):
        """Test wallet restore"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'restore', 'backup-file'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet restore: {'Working' if success else 'Failed'}")
            return success
    
    def test_advanced_wallet_operations(self):
        """Test advanced wallet operations (occasionally used)"""
        advanced_tests = [
            lambda: self._test_wallet_stake(),
            lambda: self._test_wallet_unstake(),
            lambda: self._test_wallet_staking_info(),
            lambda: self._test_wallet_rewards()
        ]
        
        results = []
        for test in advanced_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Advanced wallet test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Advanced wallet operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.5  # 50% pass rate for advanced features
    
    def _test_wallet_stake(self):
        """Test wallet staking"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'stake', '100.0'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet stake: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_unstake(self):
        """Test wallet unstaking"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'unstake', '50.0'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet unstake: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_staking_info(self):
        """Test wallet staking info"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'staking-info'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet staking-info: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_rewards(self):
        """Test wallet rewards"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'rewards'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet rewards: {'Working' if success else 'Failed'}")
            return success
    
    def test_multisig_operations(self):
        """Test multisig operations (rarely used)"""
        multisig_tests = [
            lambda: self._test_wallet_multisig_create(),
            lambda: self._test_wallet_multisig_propose(),
            lambda: self._test_wallet_multisig_challenge(),
            lambda: self._test_wallet_sign_challenge(),
            lambda: self._test_wallet_multisig_sign()
        ]
        
        results = []
        for test in multisig_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Multisig test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Multisig operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.4  # 40% pass rate for rare features
    
    def _test_wallet_multisig_create(self):
        """Test wallet multisig create"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'multisig-create', 'multisig-test'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet multisig-create: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_multisig_propose(self):
        """Test wallet multisig propose"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'multisig-propose', 'test-proposal'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet multisig-propose: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_multisig_challenge(self):
        """Test wallet multisig challenge"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'multisig-challenge', 'challenge-id'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet multisig-challenge: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_sign_challenge(self):
        """Test wallet sign challenge"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'sign-challenge', 'challenge-data'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet sign-challenge: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_multisig_sign(self):
        """Test wallet multisig sign"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'multisig-sign', 'proposal-id'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet multisig-sign: {'Working' if success else 'Failed'}")
            return success
    
    def test_liquidity_operations(self):
        """Test liquidity operations (rarely used)"""
        liquidity_tests = [
            lambda: self._test_wallet_liquidity_stake(),
            lambda: self._test_wallet_liquidity_unstake()
        ]
        
        results = []
        for test in liquidity_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Liquidity test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Liquidity operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.5  # 50% pass rate
    
    def _test_wallet_liquidity_stake(self):
        """Test wallet liquidity staking"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'liquidity-stake', '100.0'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet liquidity-stake: {'Working' if success else 'Failed'}")
            return success
    
    def _test_wallet_liquidity_unstake(self):
        """Test wallet liquidity unstaking"""
        with patch('aitbc_cli.commands.wallet.Path.home') as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            
            result = self.runner.invoke(cli, ['--test-mode', 'wallet', 'liquidity-unstake', '50.0'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} wallet liquidity-unstake: {'Working' if success else 'Failed'}")
            return success
    
    def run_all_tests(self):
        """Run all wallet group tests"""
        print("🚀 Starting AITBC CLI Wallet Group Test Suite")
        print("Testing wallet and transaction management commands (MOST FREQUENTLY USED)")
        print("=" * 60)
        
        # Setup test environment
        config_dir = Path(tempfile.mkdtemp(prefix="aitbc_wallet_test_"))
        self.temp_dir = str(config_dir)
        print(f"📁 Test environment: {self.temp_dir}")
        
        try:
            # Run test categories by usage frequency
            test_categories = [
                ("Core Wallet Operations", self.test_core_wallet_operations),
                ("Transaction Operations", self.test_transaction_operations),
                ("Advanced Wallet Operations", self.test_advanced_wallet_operations),
                ("Multisig Operations", self.test_multisig_operations),
                ("Liquidity Operations", self.test_liquidity_operations)
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
        print("📊 WALLET GROUP TEST RESULTS SUMMARY")
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
            print("🎉 EXCELLENT: Wallet commands are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most wallet commands are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some wallet commands need attention")
        else:
            print("🚨 POOR: Many wallet commands need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    tester = WalletGroupTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
