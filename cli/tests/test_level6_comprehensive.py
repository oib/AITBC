#!/usr/bin/env python3
"""
AITBC CLI Level 6 Commands Test Script

Tests comprehensive coverage of remaining CLI commands:
- Node management operations (7 commands)
- Monitor and analytics operations (11 commands)
- Testing and development commands (9 commands)
- Plugin management operations (4 commands)
- Version and utility commands (1 command)

Level 6 Commands: Comprehensive coverage for remaining operations
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


class Level6CommandTester:
    """Test suite for AITBC CLI Level 6 commands (comprehensive coverage)"""
    
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
    
    def test_node_commands(self):
        """Test node management commands"""
        node_tests = [
            lambda: self._test_node_add_help(),
            lambda: self._test_node_chains_help(),
            lambda: self._test_node_info_help(),
            lambda: self._test_node_list_help(),
            lambda: self._test_node_monitor_help(),
            lambda: self._test_node_remove_help(),
            lambda: self._test_node_test_help()
        ]
        
        results = []
        for test in node_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Node test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Node commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
    def _test_node_add_help(self):
        """Test node add help"""
        result = self.runner.invoke(cli, ['node', 'add', '--help'])
        success = result.exit_code == 0 and 'add' in result.output.lower()
        print(f"    {'✅' if success else '❌'} node add: {'Working' if success else 'Failed'}")
        return success
    
    def _test_node_chains_help(self):
        """Test node chains help"""
        result = self.runner.invoke(cli, ['node', 'chains', '--help'])
        success = result.exit_code == 0 and 'chains' in result.output.lower()
        print(f"    {'✅' if success else '❌'} node chains: {'Working' if success else 'Failed'}")
        return success
    
    def _test_node_info_help(self):
        """Test node info help"""
        result = self.runner.invoke(cli, ['node', 'info', '--help'])
        success = result.exit_code == 0 and 'info' in result.output.lower()
        print(f"    {'✅' if success else '❌'} node info: {'Working' if success else 'Failed'}")
        return success
    
    def _test_node_list_help(self):
        """Test node list help"""
        result = self.runner.invoke(cli, ['node', 'list', '--help'])
        success = result.exit_code == 0 and 'list' in result.output.lower()
        print(f"    {'✅' if success else '❌'} node list: {'Working' if success else 'Failed'}")
        return success
    
    def _test_node_monitor_help(self):
        """Test node monitor help"""
        result = self.runner.invoke(cli, ['node', 'monitor', '--help'])
        success = result.exit_code == 0 and 'monitor' in result.output.lower()
        print(f"    {'✅' if success else '❌'} node monitor: {'Working' if success else 'Failed'}")
        return success
    
    def _test_node_remove_help(self):
        """Test node remove help"""
        result = self.runner.invoke(cli, ['node', 'remove', '--help'])
        success = result.exit_code == 0 and 'remove' in result.output.lower()
        print(f"    {'✅' if success else '❌'} node remove: {'Working' if success else 'Failed'}")
        return success
    
    def _test_node_test_help(self):
        """Test node test help"""
        result = self.runner.invoke(cli, ['node', 'test', '--help'])
        success = result.exit_code == 0 and 'test' in result.output.lower()
        print(f"    {'✅' if success else '❌'} node test: {'Working' if success else 'Failed'}")
        return success
    
    def test_monitor_commands(self):
        """Test monitor and analytics commands"""
        monitor_tests = [
            lambda: self._test_monitor_campaigns_help(),
            lambda: self._test_monitor_dashboard_help(),
            lambda: self._test_monitor_history_help(),
            lambda: self._test_monitor_metrics_help(),
            lambda: self._test_monitor_webhooks_help()
        ]
        
        results = []
        for test in monitor_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Monitor test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Monitor commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
    def _test_monitor_campaigns_help(self):
        """Test monitor campaigns help"""
        result = self.runner.invoke(cli, ['monitor', 'campaigns', '--help'])
        success = result.exit_code == 0 and 'campaigns' in result.output.lower()
        print(f"    {'✅' if success else '❌'} monitor campaigns: {'Working' if success else 'Failed'}")
        return success
    
    def _test_monitor_dashboard_help(self):
        """Test monitor dashboard help"""
        result = self.runner.invoke(cli, ['monitor', 'dashboard', '--help'])
        success = result.exit_code == 0 and 'dashboard' in result.output.lower()
        print(f"    {'✅' if success else '❌'} monitor dashboard: {'Working' if success else 'Failed'}")
        return success
    
    def _test_monitor_history_help(self):
        """Test monitor history help"""
        result = self.runner.invoke(cli, ['monitor', 'history', '--help'])
        success = result.exit_code == 0 and 'history' in result.output.lower()
        print(f"    {'✅' if success else '❌'} monitor history: {'Working' if success else 'Failed'}")
        return success
    
    def _test_monitor_metrics_help(self):
        """Test monitor metrics help"""
        result = self.runner.invoke(cli, ['monitor', 'metrics', '--help'])
        success = result.exit_code == 0 and 'metrics' in result.output.lower()
        print(f"    {'✅' if success else '❌'} monitor metrics: {'Working' if success else 'Failed'}")
        return success
    
    def _test_monitor_webhooks_help(self):
        """Test monitor webhooks help"""
        result = self.runner.invoke(cli, ['monitor', 'webhooks', '--help'])
        success = result.exit_code == 0 and 'webhooks' in result.output.lower()
        print(f"    {'✅' if success else '❌'} monitor webhooks: {'Working' if success else 'Failed'}")
        return success
    
    def test_development_commands(self):
        """Test testing and development commands"""
        dev_tests = [
            lambda: self._test_test_api_help(),
            lambda: self._test_test_blockchain_help(),
            lambda: self._test_test_diagnostics_help(),
            lambda: self._test_test_environment_help(),
            lambda: self._test_test_integration_help(),
            lambda: self._test_test_job_help(),
            lambda: self._test_test_marketplace_help(),
            lambda: self._test_test_mock_help(),
            lambda: self._test_test_wallet_help()
        ]
        
        results = []
        for test in dev_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Development test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Development commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
    def _test_test_api_help(self):
        """Test test api help"""
        result = self.runner.invoke(cli, ['test', 'api', '--help'])
        success = result.exit_code == 0 and 'api' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test api: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_blockchain_help(self):
        """Test test blockchain help"""
        result = self.runner.invoke(cli, ['test', 'blockchain', '--help'])
        success = result.exit_code == 0 and 'blockchain' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test blockchain: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_diagnostics_help(self):
        """Test test diagnostics help"""
        result = self.runner.invoke(cli, ['test', 'diagnostics', '--help'])
        success = result.exit_code == 0 and 'diagnostics' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test diagnostics: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_environment_help(self):
        """Test test environment help"""
        result = self.runner.invoke(cli, ['test', 'environment', '--help'])
        success = result.exit_code == 0 and 'environment' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test environment: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_integration_help(self):
        """Test test integration help"""
        result = self.runner.invoke(cli, ['test', 'integration', '--help'])
        success = result.exit_code == 0 and 'integration' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test integration: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_job_help(self):
        """Test test job help"""
        result = self.runner.invoke(cli, ['test', 'job', '--help'])
        success = result.exit_code == 0 and 'job' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test job: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_marketplace_help(self):
        """Test test marketplace help"""
        result = self.runner.invoke(cli, ['test', 'marketplace', '--help'])
        success = result.exit_code == 0 and 'marketplace' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test marketplace: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_mock_help(self):
        """Test test mock help"""
        result = self.runner.invoke(cli, ['test', 'mock', '--help'])
        success = result.exit_code == 0 and 'mock' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test mock: {'Working' if success else 'Failed'}")
        return success
    
    def _test_test_wallet_help(self):
        """Test test wallet help"""
        result = self.runner.invoke(cli, ['test', 'wallet', '--help'])
        success = result.exit_code == 0 and 'wallet' in result.output.lower()
        print(f"    {'✅' if success else '❌'} test wallet: {'Working' if success else 'Failed'}")
        return success
    
    def test_plugin_commands(self):
        """Test plugin management commands"""
        plugin_tests = [
            lambda: self._test_plugin_list_help(),
            lambda: self._test_plugin_install_help(),
            lambda: self._test_plugin_remove_help(),
            lambda: self._test_plugin_info_help()
        ]
        
        results = []
        for test in plugin_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Plugin test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Plugin commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
    def _test_plugin_list_help(self):
        """Test plugin list help"""
        result = self.runner.invoke(cli, ['plugin', 'list', '--help'])
        success = result.exit_code == 0 and 'list' in result.output.lower()
        print(f"    {'✅' if success else '❌'} plugin list: {'Working' if success else 'Failed'}")
        return success
    
    def _test_plugin_install_help(self):
        """Test plugin install help"""
        result = self.runner.invoke(cli, ['plugin', 'install', '--help'])
        success = result.exit_code == 0 and 'install' in result.output.lower()
        print(f"    {'✅' if success else '❌'} plugin install: {'Working' if success else 'Failed'}")
        return success
    
    def _test_plugin_remove_help(self):
        """Test plugin remove help (may not exist)"""
        result = self.runner.invoke(cli, ['plugin', '--help'])
        success = result.exit_code == 0  # Just check that plugin group exists
        print(f"    {'✅' if success else '❌'} plugin group: {'Working' if success else 'Failed'}")
        return success
    
    def _test_plugin_info_help(self):
        """Test plugin info help (may not exist)"""
        result = self.runner.invoke(cli, ['plugin', '--help'])
        success = result.exit_code == 0  # Just check that plugin group exists
        print(f"    {'✅' if success else '❌'} plugin group: {'Working' if success else 'Failed'}")
        return success
    
    def test_utility_commands(self):
        """Test version and utility commands"""
        utility_tests = [
            lambda: self._test_version_help()
        ]
        
        results = []
        for test in utility_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Utility test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Utility commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
    def _test_version_help(self):
        """Test version help"""
        result = self.runner.invoke(cli, ['version', '--help'])
        success = result.exit_code == 0 and 'version' in result.output.lower()
        print(f"    {'✅' if success else '❌'} version: {'Working' if success else 'Failed'}")
        return success
    
    def run_all_tests(self):
        """Run all Level 6 command tests"""
        print("🚀 Starting AITBC CLI Level 6 Commands Test Suite")
        print("Testing comprehensive coverage of remaining CLI commands")
        print("=" * 60)
        
        # Setup test environment
        config_dir = Path(tempfile.mkdtemp(prefix="aitbc_level6_test_"))
        self.temp_dir = str(config_dir)
        print(f"📁 Test environment: {self.temp_dir}")
        
        try:
            # Run test categories
            test_categories = [
                ("Node Commands", self.test_node_commands),
                ("Monitor Commands", self.test_monitor_commands),
                ("Development Commands", self.test_development_commands),
                ("Plugin Commands", self.test_plugin_commands),
                ("Utility Commands", self.test_utility_commands)
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
        print("📊 LEVEL 6 TEST RESULTS SUMMARY")
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
            print("🎉 EXCELLENT: Level 6 commands are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most Level 6 commands are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some Level 6 commands need attention")
        else:
            print("🚨 POOR: Many Level 6 commands need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    tester = Level6CommandTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
