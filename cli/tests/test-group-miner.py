#!/usr/bin/env python3
"""
AITBC CLI Miner Group Test Script

Tests mining operations and job processing (HIGH FREQUENCY):
- miner register, status, earnings, jobs, deregister
- miner mine-ollama, mine-custom, mine-ai
- miner config, logs, performance

Usage Frequency: DAILY - Mining operations
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


class MinerGroupTester:
    """Test suite for AITBC CLI miner commands (high frequency)"""
    
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
    
    def test_core_miner_operations(self):
        """Test core miner operations (high frequency)"""
        core_tests = [
            lambda: self._test_miner_register(),
            lambda: self._test_miner_status(),
            lambda: self._test_miner_earnings(),
            lambda: self._test_miner_jobs(),
            lambda: self._test_miner_deregister()
        ]
        
        results = []
        for test in core_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Core miner test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Core miner operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate for daily operations
    
    def _test_miner_register(self):
        """Test miner registration"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'miner_id': 'miner_test123',
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
    
    def test_mining_operations(self):
        """Test mining operations (medium frequency)"""
        mining_tests = [
            lambda: self._test_miner_mine_ollama(),
            lambda: self._test_miner_mine_custom(),
            lambda: self._test_miner_mine_ai()
        ]
        
        results = []
        for test in mining_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Mining test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Mining operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
    def _test_miner_mine_ollama(self):
        """Test mine ollama"""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = 'Available models: gemma3:1b, llama3:8b'
            mock_run.return_value = mock_result
            
            result = self.runner.invoke(cli, ['miner', 'mine-ollama', '--jobs', '1', '--miner-id', 'test', '--model', 'gemma3:1b'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner mine-ollama: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_mine_custom(self):
        """Test mine custom"""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = 'Custom mining started'
            mock_run.return_value = mock_result
            
            result = self.runner.invoke(cli, ['miner', 'mine-custom', '--config', 'custom.yaml'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner mine-custom: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_mine_ai(self):
        """Test mine ai"""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = 'AI mining started'
            mock_run.return_value = mock_result
            
            result = self.runner.invoke(cli, ['miner', 'mine-ai', '--model', 'custom-model'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner mine-ai: {'Working' if success else 'Failed'}")
            return success
    
    def test_miner_management(self):
        """Test miner management operations (occasionally used)"""
        management_tests = [
            lambda: self._test_miner_config(),
            lambda: self._test_miner_logs(),
            lambda: self._test_miner_performance()
        ]
        
        results = []
        for test in management_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Management test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Miner management: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.6  # 60% pass rate for management features
    
    def _test_miner_config(self):
        """Test miner config"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'gpu_name': 'RTX 4090',
                'max_jobs': 2,
                'memory_limit': '20GB'
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'config'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner config: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_logs(self):
        """Test miner logs"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'logs': [
                    {'timestamp': '2026-01-01T00:00:00Z', 'level': 'INFO', 'message': 'Miner started'},
                    {'timestamp': '2026-01-01T00:01:00Z', 'level': 'INFO', 'message': 'Job received'}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'logs'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner logs: {'Working' if success else 'Failed'}")
            return success
    
    def _test_miner_performance(self):
        """Test miner performance"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'gpu_utilization': 85.0,
                'memory_usage': 15.0,
                'temperature': 75.0,
                'jobs_per_hour': 10.5
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['miner', 'performance'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} miner performance: {'Working' if success else 'Failed'}")
            return success
    
    def run_all_tests(self):
        """Run all miner group tests"""
        print("🚀 Starting AITBC CLI Miner Group Test Suite")
        print("Testing mining operations and job processing (HIGH FREQUENCY)")
        print("=" * 60)
        
        # Setup test environment
        config_dir = Path(tempfile.mkdtemp(prefix="aitbc_miner_test_"))
        self.temp_dir = str(config_dir)
        print(f"📁 Test environment: {self.temp_dir}")
        
        try:
            # Run test categories by usage frequency
            test_categories = [
                ("Core Miner Operations", self.test_core_miner_operations),
                ("Mining Operations", self.test_mining_operations),
                ("Miner Management", self.test_miner_management)
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
        print("📊 MINER GROUP TEST RESULTS SUMMARY")
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
            print("🎉 EXCELLENT: Miner commands are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most miner commands are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some miner commands need attention")
        else:
            print("🚨 POOR: Many miner commands need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    tester = MinerGroupTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
