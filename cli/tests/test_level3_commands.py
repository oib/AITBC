#!/usr/bin/env python3
"""
AITBC CLI Level 3 Commands Test Script

Tests advanced features and complex operations:
- Agent workflows and AI operations (9 commands)
- Governance and voting (4 commands)
- Deployment and scaling (6 commands)
- Multi-chain operations (6 commands)
- Multi-modal processing (8 commands)

Level 3 Commands: Advanced features for power users
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


class Level3CommandTester:
    """Test suite for AITBC CLI Level 3 commands (advanced features)"""
    
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
    
    def test_agent_commands(self):
        """Test advanced AI agent workflow commands"""
        agent_tests = [
            # Core agent operations
            lambda: self._test_agent_create_help(),
            lambda: self._test_agent_execute_help(),
            lambda: self._test_agent_list_help(),
            lambda: self._test_agent_status_help(),
            lambda: self._test_agent_receipt_help(),
            # Agent network operations
            lambda: self._test_agent_network_create_help(),
            lambda: self._test_agent_network_execute_help(),
            lambda: self._test_agent_network_status_help(),
            lambda: self._test_agent_learning_enable_help()
        ]
        
        results = []
        for test in agent_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Agent test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Agent commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.75  # 75% pass rate
    
    def _test_agent_create_help(self):
        """Test agent create help"""
        result = self.runner.invoke(cli, ['agent', 'create', '--help'])
        success = result.exit_code == 0 and 'create' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent create: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_execute_help(self):
        """Test agent execute help"""
        result = self.runner.invoke(cli, ['agent', 'execute', '--help'])
        success = result.exit_code == 0 and 'execute' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent execute: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_list_help(self):
        """Test agent list help"""
        result = self.runner.invoke(cli, ['agent', 'list', '--help'])
        success = result.exit_code == 0 and 'list' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent list: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_status_help(self):
        """Test agent status help"""
        result = self.runner.invoke(cli, ['agent', 'status', '--help'])
        success = result.exit_code == 0 and 'status' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent status: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_receipt_help(self):
        """Test agent receipt help"""
        result = self.runner.invoke(cli, ['agent', 'receipt', '--help'])
        success = result.exit_code == 0 and 'receipt' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent receipt: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_network_create_help(self):
        """Test agent network create help"""
        result = self.runner.invoke(cli, ['agent', 'network', 'create', '--help'])
        success = result.exit_code == 0 and 'create' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent network create: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_network_execute_help(self):
        """Test agent network execute help"""
        result = self.runner.invoke(cli, ['agent', 'network', 'execute', '--help'])
        success = result.exit_code == 0 and 'execute' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent network execute: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_network_status_help(self):
        """Test agent network status help"""
        result = self.runner.invoke(cli, ['agent', 'network', 'status', '--help'])
        success = result.exit_code == 0 and 'status' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent network status: {'Working' if success else 'Failed'}")
        return success
    
    def _test_agent_learning_enable_help(self):
        """Test agent learning enable help"""
        result = self.runner.invoke(cli, ['agent', 'learning', 'enable', '--help'])
        success = result.exit_code == 0 and 'enable' in result.output.lower()
        print(f"    {'✅' if success else '❌'} agent learning enable: {'Working' if success else 'Failed'}")
        return success
    
    def test_governance_commands(self):
        """Test governance and voting commands"""
        governance_tests = [
            lambda: self._test_governance_list_help(),
            lambda: self._test_governance_propose_help(),
            lambda: self._test_governance_vote_help(),
            lambda: self._test_governance_result_help()
        ]
        
        results = []
        for test in governance_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Governance test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Governance commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.75  # 75% pass rate
    
    def _test_governance_list_help(self):
        """Test governance list help"""
        result = self.runner.invoke(cli, ['governance', 'list', '--help'])
        success = result.exit_code == 0 and 'list' in result.output.lower()
        print(f"    {'✅' if success else '❌'} governance list: {'Working' if success else 'Failed'}")
        return success
    
    def _test_governance_propose_help(self):
        """Test governance propose help"""
        result = self.runner.invoke(cli, ['governance', 'propose', '--help'])
        success = result.exit_code == 0 and 'propose' in result.output.lower()
        print(f"    {'✅' if success else '❌'} governance propose: {'Working' if success else 'Failed'}")
        return success
    
    def _test_governance_vote_help(self):
        """Test governance vote help"""
        result = self.runner.invoke(cli, ['governance', 'vote', '--help'])
        success = result.exit_code == 0 and 'vote' in result.output.lower()
        print(f"    {'✅' if success else '❌'} governance vote: {'Working' if success else 'Failed'}")
        return success
    
    def _test_governance_result_help(self):
        """Test governance result help"""
        result = self.runner.invoke(cli, ['governance', 'result', '--help'])
        success = result.exit_code == 0 and 'result' in result.output.lower()
        print(f"    {'✅' if success else '❌'} governance result: {'Working' if success else 'Failed'}")
        return success
    
    def test_deploy_commands(self):
        """Test deployment and scaling commands"""
        deploy_tests = [
            lambda: self._test_deploy_create_help(),
            lambda: self._test_deploy_start_help(),
            lambda: self._test_deploy_status_help(),
            lambda: self._test_deploy_stop_help(),
            lambda: self._test_deploy_auto_scale_help(),
            lambda: self._test_deploy_list_deployments_help()
        ]
        
        results = []
        for test in deploy_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Deploy test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Deploy commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.75  # 75% pass rate
    
    def _test_deploy_create_help(self):
        """Test deploy create help"""
        result = self.runner.invoke(cli, ['deploy', 'create', '--help'])
        success = result.exit_code == 0 and 'create' in result.output.lower()
        print(f"    {'✅' if success else '❌'} deploy create: {'Working' if success else 'Failed'}")
        return success
    
    def _test_deploy_start_help(self):
        """Test deploy start help"""
        result = self.runner.invoke(cli, ['deploy', 'start', '--help'])
        success = result.exit_code == 0 and 'start' in result.output.lower()
        print(f"    {'✅' if success else '❌'} deploy start: {'Working' if success else 'Failed'}")
        return success
    
    def _test_deploy_status_help(self):
        """Test deploy status help"""
        result = self.runner.invoke(cli, ['deploy', 'status', '--help'])
        success = result.exit_code == 0 and 'status' in result.output.lower()
        print(f"    {'✅' if success else '❌'} deploy status: {'Working' if success else 'Failed'}")
        return success
    
    def _test_deploy_stop_help(self):
        """Test deploy stop help"""
        result = self.runner.invoke(cli, ['deploy', 'stop', '--help'])
        success = result.exit_code == 0 and 'stop' in result.output.lower()
        print(f"    {'✅' if success else '❌'} deploy stop: {'Working' if success else 'Failed'}")
        return success
    
    def _test_deploy_auto_scale_help(self):
        """Test deploy auto-scale help"""
        result = self.runner.invoke(cli, ['deploy', 'auto-scale', '--help'])
        success = result.exit_code == 0 and 'auto-scale' in result.output.lower()
        print(f"    {'✅' if success else '❌'} deploy auto-scale: {'Working' if success else 'Failed'}")
        return success
    
    def _test_deploy_list_deployments_help(self):
        """Test deploy list-deployments help"""
        result = self.runner.invoke(cli, ['deploy', 'list-deployments', '--help'])
        success = result.exit_code == 0 and 'list' in result.output.lower()
        print(f"    {'✅' if success else '❌'} deploy list-deployments: {'Working' if success else 'Failed'}")
        return success
    
    def test_chain_commands(self):
        """Test multi-chain operations commands"""
        chain_tests = [
            lambda: self._test_chain_create_help(),
            lambda: self._test_chain_list_help(),
            lambda: self._test_chain_status_help(),
            lambda: self._test_chain_add_help(),
            lambda: self._test_chain_remove_help(),
            lambda: self._test_chain_backup_help()
        ]
        
        results = []
        for test in chain_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Chain test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Chain commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.75  # 75% pass rate
    
    def _test_chain_create_help(self):
        """Test chain create help"""
        result = self.runner.invoke(cli, ['chain', 'create', '--help'])
        success = result.exit_code == 0 and 'create' in result.output.lower()
        print(f"    {'✅' if success else '❌'} chain create: {'Working' if success else 'Failed'}")
        return success
    
    def _test_chain_list_help(self):
        """Test chain list help"""
        result = self.runner.invoke(cli, ['chain', 'list', '--help'])
        success = result.exit_code == 0 and 'list' in result.output.lower()
        print(f"    {'✅' if success else '❌'} chain list: {'Working' if success else 'Failed'}")
        return success
    
    def _test_chain_status_help(self):
        """Test chain status help"""
        result = self.runner.invoke(cli, ['chain', 'status', '--help'])
        success = result.exit_code == 0 and 'status' in result.output.lower()
        print(f"    {'✅' if success else '❌'} chain status: {'Working' if success else 'Failed'}")
        return success
    
    def _test_chain_add_help(self):
        """Test chain add help"""
        result = self.runner.invoke(cli, ['chain', 'add', '--help'])
        success = result.exit_code == 0 and 'add' in result.output.lower()
        print(f"    {'✅' if success else '❌'} chain add: {'Working' if success else 'Failed'}")
        return success
    
    def _test_chain_remove_help(self):
        """Test chain remove help"""
        result = self.runner.invoke(cli, ['chain', 'remove', '--help'])
        success = result.exit_code == 0 and 'remove' in result.output.lower()
        print(f"    {'✅' if success else '❌'} chain remove: {'Working' if success else 'Failed'}")
        return success
    
    def _test_chain_backup_help(self):
        """Test chain backup help"""
        result = self.runner.invoke(cli, ['chain', 'backup', '--help'])
        success = result.exit_code == 0 and 'backup' in result.output.lower()
        print(f"    {'✅' if success else '❌'} chain backup: {'Working' if success else 'Failed'}")
        return success
    
    def test_multimodal_commands(self):
        """Test multi-modal processing commands"""
        multimodal_tests = [
            lambda: self._test_multimodal_agent_help(),
            lambda: self._test_multimodal_process_help(),
            lambda: self._test_multimodal_convert_help(),
            lambda: self._test_multimodal_test_help(),
            lambda: self._test_multimodal_optimize_help(),
            lambda: self._test_multimodal_attention_help(),
            lambda: self._test_multimodal_benchmark_help(),
            lambda: self._test_multimodal_capabilities_help()
        ]
        
        results = []
        for test in multimodal_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Multimodal test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Multimodal commands: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.75  # 75% pass rate
    
    def _test_multimodal_agent_help(self):
        """Test multimodal agent help"""
        result = self.runner.invoke(cli, ['multimodal', 'agent', '--help'])
        success = result.exit_code == 0 and 'agent' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal agent: {'Working' if success else 'Failed'}")
        return success
    
    def _test_multimodal_process_help(self):
        """Test multimodal process help"""
        result = self.runner.invoke(cli, ['multimodal', 'process', '--help'])
        success = result.exit_code == 0 and 'process' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal process: {'Working' if success else 'Failed'}")
        return success
    
    def _test_multimodal_convert_help(self):
        """Test multimodal convert help"""
        result = self.runner.invoke(cli, ['multimodal', 'convert', '--help'])
        success = result.exit_code == 0 and 'convert' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal convert: {'Working' if success else 'Failed'}")
        return success
    
    def _test_multimodal_test_help(self):
        """Test multimodal test help"""
        result = self.runner.invoke(cli, ['multimodal', 'test', '--help'])
        success = result.exit_code == 0 and 'test' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal test: {'Working' if success else 'Failed'}")
        return success
    
    def _test_multimodal_optimize_help(self):
        """Test multimodal optimize help"""
        result = self.runner.invoke(cli, ['multimodal', 'optimize', '--help'])
        success = result.exit_code == 0 and 'optimize' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal optimize: {'Working' if success else 'Failed'}")
        return success
    
    def _test_multimodal_attention_help(self):
        """Test multimodal attention help"""
        result = self.runner.invoke(cli, ['multimodal', 'attention', '--help'])
        success = result.exit_code == 0 and 'attention' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal attention: {'Working' if success else 'Failed'}")
        return success
    
    def _test_multimodal_benchmark_help(self):
        """Test multimodal benchmark help"""
        result = self.runner.invoke(cli, ['multimodal', 'benchmark', '--help'])
        success = result.exit_code == 0 and 'benchmark' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal benchmark: {'Working' if success else 'Failed'}")
        return success
    
    def _test_multimodal_capabilities_help(self):
        """Test multimodal capabilities help"""
        result = self.runner.invoke(cli, ['multimodal', 'capabilities', '--help'])
        success = result.exit_code == 0 and 'capabilities' in result.output.lower()
        print(f"    {'✅' if success else '❌'} multimodal capabilities: {'Working' if success else 'Failed'}")
        return success
    
    def run_all_tests(self):
        """Run all Level 3 command tests"""
        print("🚀 Starting AITBC CLI Level 3 Commands Test Suite")
        print("Testing advanced features for power users")
        print("=" * 60)
        
        # Setup test environment
        config_dir = Path(tempfile.mkdtemp(prefix="aitbc_level3_test_"))
        self.temp_dir = str(config_dir)
        print(f"📁 Test environment: {self.temp_dir}")
        
        try:
            # Run test categories
            test_categories = [
                ("Agent Commands", self.test_agent_commands),
                ("Governance Commands", self.test_governance_commands),
                ("Deploy Commands", self.test_deploy_commands),
                ("Chain Commands", self.test_chain_commands),
                ("Multimodal Commands", self.test_multimodal_commands)
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
        print("📊 LEVEL 3 TEST RESULTS SUMMARY")
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
            print("🎉 EXCELLENT: Level 3 commands are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most Level 3 commands are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some Level 3 commands need attention")
        else:
            print("🚨 POOR: Many Level 3 commands need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    tester = Level3CommandTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
