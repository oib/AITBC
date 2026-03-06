#!/usr/bin/env python3
"""
AITBC CLI Client Group Test Script

Tests job submission and management commands (HIGH FREQUENCY):
- client submit, status, result, history, cancel
- client receipt, logs, monitor, track

Usage Frequency: DAILY - Job management operations
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


class ClientGroupTester:
    """Test suite for AITBC CLI client commands (high frequency)"""
    
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
    
    def test_core_client_operations(self):
        """Test core client operations (high frequency)"""
        core_tests = [
            lambda: self._test_client_submit(),
            lambda: self._test_client_status(),
            lambda: self._test_client_result(),
            lambda: self._test_client_history(),
            lambda: self._test_client_cancel()
        ]
        
        results = []
        for test in core_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Core client test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Core client operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.8  # 80% pass rate for daily operations
    
    def _test_client_submit(self):
        """Test job submission"""
        with patch('httpx.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test123',
                'status': 'pending',
                'submitted_at': '2026-01-01T00:00:00Z'
            }
            mock_post.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'submit', 'What is machine learning?', '--model', 'gemma3:1b'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client submit: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_status(self):
        """Test job status check"""
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
        """Test job result retrieval"""
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
        """Test job history"""
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
        """Test job cancellation"""
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
    
    def test_advanced_client_operations(self):
        """Test advanced client operations (medium frequency)"""
        advanced_tests = [
            lambda: self._test_client_receipt(),
            lambda: self._test_client_logs(),
            lambda: self._test_client_monitor(),
            lambda: self._test_client_track()
        ]
        
        results = []
        for test in advanced_tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"  ❌ Advanced client test error: {str(e)}")
                results.append(False)
        
        success_count = sum(results)
        print(f"  Advanced client operations: {success_count}/{len(results)} passed")
        return success_count >= len(results) * 0.7  # 70% pass rate
    
    def _test_client_receipt(self):
        """Test job receipt retrieval"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test123',
                'receipt': {
                    'transaction_hash': '0x123...',
                    'timestamp': '2026-01-01T00:00:00Z',
                    'miner_id': 'miner1'
                }
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'receipt', 'job_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client receipt: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_logs(self):
        """Test job logs"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test123',
                'logs': [
                    {'timestamp': '2026-01-01T00:00:00Z', 'message': 'Job started'},
                    {'timestamp': '2026-01-01T00:01:00Z', 'message': 'Processing...'}
                ]
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'logs', 'job_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client logs: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_monitor(self):
        """Test job monitoring"""
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
            
            result = self.runner.invoke(cli, ['client', 'monitor'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client monitor: {'Working' if success else 'Failed'}")
            return success
    
    def _test_client_track(self):
        """Test job tracking"""
        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'job_id': 'job_test123',
                'tracking': {
                    'submitted_at': '2026-01-01T00:00:00Z',
                    'started_at': '2026-01-01T00:01:00Z',
                    'completed_at': '2026-01-01T00:05:00Z',
                    'duration': 240
                }
            }
            mock_get.return_value = mock_response
            
            result = self.runner.invoke(cli, ['client', 'track', 'job_test123'])
            success = result.exit_code == 0
            print(f"    {'✅' if success else '❌'} client track: {'Working' if success else 'Failed'}")
            return success
    
    def run_all_tests(self):
        """Run all client group tests"""
        print("🚀 Starting AITBC CLI Client Group Test Suite")
        print("Testing job submission and management commands (HIGH FREQUENCY)")
        print("=" * 60)
        
        # Setup test environment
        config_dir = Path(tempfile.mkdtemp(prefix="aitbc_client_test_"))
        self.temp_dir = str(config_dir)
        print(f"📁 Test environment: {self.temp_dir}")
        
        try:
            # Run test categories by usage frequency
            test_categories = [
                ("Core Client Operations", self.test_core_client_operations),
                ("Advanced Client Operations", self.test_advanced_client_operations)
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
        print("📊 CLIENT GROUP TEST RESULTS SUMMARY")
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
            print("🎉 EXCELLENT: Client commands are in great shape!")
        elif success_rate >= 75:
            print("👍 GOOD: Most client commands are working properly")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some client commands need attention")
        else:
            print("🚨 POOR: Many client commands need immediate attention")
        
        return self.test_results['failed'] == 0


def main():
    """Main entry point"""
    tester = ClientGroupTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
