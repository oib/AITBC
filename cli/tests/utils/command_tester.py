"""
Command tester utility for AITBC CLI testing
"""

import time
from typing import List, Dict, Any, Optional, Callable
from click.testing import CliRunner
from .test_helpers import CommandTestResult, run_command_test, TestEnvironment


class CommandTester:
    """Enhanced command tester for AITBC CLI"""
    
    def __init__(self, cli_app):
        self.runner = CliRunner()
        self.cli = cli_app
        self.test_env = TestEnvironment()
        self.results: List[CommandTestResult] = []
        self.setup_mocks()
    
    def setup_mocks(self):
        """Setup common test mocks"""
        self.mocks = setup_test_mocks(self.test_env)
        
        # Setup default API responses
        self.api_responses = mock_api_responses()
        
        # Configure default mock responses
        if 'httpx' in self.mocks:
            self.mocks['httpx'].return_value = MockApiResponse.success_response(
                self.api_responses['blockchain_info']
            )
    
    def cleanup(self):
        """Cleanup test environment"""
        self.test_env.cleanup()
    
    def run_command(self, command_args: List[str], 
                   expected_exit_code: int = 0,
                   expected_text: str = None,
                   timeout: int = 30) -> CommandTestResult:
        """Run a command test"""
        result = run_command_test(
            self.runner, command_args, expected_exit_code, expected_text, timeout
        )
        self.results.append(result)
        return result
    
    def test_command_help(self, command: str, subcommand: str = None) -> CommandTestResult:
        """Test command help"""
        args = [command, '--help']
        if subcommand:
            args.insert(1, subcommand)
        
        return self.run_command(args, expected_text='Usage:')
    
    def test_command_group(self, group_name: str, subcommands: List[str] = None) -> Dict[str, CommandTestResult]:
        """Test a command group and its subcommands"""
        results = {}
        
        # Test main group help
        results[f"{group_name}_help"] = self.test_command_help(group_name)
        
        # Test subcommands if provided
        if subcommands:
            for subcmd in subcommands:
                results[f"{group_name}_{subcmd}"] = self.test_command_help(group_name, subcmd)
        
        return results
    
    def test_config_commands(self) -> Dict[str, CommandTestResult]:
        """Test configuration commands"""
        results = {}
        
        # Test config show
        results['config_show'] = self.run_command(['config', 'show'])
        
        # Test config set
        results['config_set'] = self.run_command(['config', 'set', 'test_key', 'test_value'])
        
        # Test config get
        results['config_get'] = self.run_command(['config', 'get', 'test_key'])
        
        # Test config environments
        results['config_environments'] = self.run_command(['config', 'environments'])
        
        return results
    
    def test_auth_commands(self) -> Dict[str, CommandTestResult]:
        """Test authentication commands"""
        results = {}
        
        # Test auth status
        results['auth_status'] = self.run_command(['auth', 'status'])
        
        # Test auth login
        results['auth_login'] = self.run_command(['auth', 'login', 'test-api-key-12345'])
        
        # Test auth logout
        results['auth_logout'] = self.run_command(['auth', 'logout'])
        
        return results
    
    def test_wallet_commands(self) -> Dict[str, CommandTestResult]:
        """Test wallet commands"""
        results = {}
        
        # Create mock wallet directory
        wallet_dir = self.test_env.create_mock_wallet_dir()
        self.mocks['home'].return_value = wallet_dir
        
        # Test wallet list
        results['wallet_list'] = self.run_command(['--test-mode', 'wallet', 'list'])
        
        # Test wallet create (mock password)
        with patch('getpass.getpass') as mock_getpass:
            mock_getpass.return_value = 'test-password'
            results['wallet_create'] = self.run_command(['--test-mode', 'wallet', 'create', 'test-wallet'])
        
        return results
    
    def test_blockchain_commands(self) -> Dict[str, CommandTestResult]:
        """Test blockchain commands"""
        results = {}
        
        # Setup blockchain API mocks
        self.mocks['httpx'].return_value = MockApiResponse.success_response(
            self.api_responses['blockchain_info']
        )
        
        # Test blockchain info
        results['blockchain_info'] = self.run_command(['--test-mode', 'blockchain', 'info'])
        
        # Test blockchain status
        self.mocks['httpx'].return_value = MockApiResponse.success_response(
            self.api_responses['blockchain_status']
        )
        results['blockchain_status'] = self.run_command(['--test-mode', 'blockchain', 'status'])
        
        return results
    
    def test_utility_commands(self) -> Dict[str, CommandTestResult]:
        """Test utility commands"""
        results = {}
        
        # Test version
        results['version'] = self.run_command(['version'])
        
        # Test main help
        results['help'] = self.run_command(['--help'])
        
        return results
    
    def run_comprehensive_test(self) -> Dict[str, Dict[str, CommandTestResult]]:
        """Run comprehensive test suite"""
        print("🚀 Running Comprehensive AITBC CLI Test Suite")
        
        all_results = {}
        
        # Test core command groups
        print("\n📂 Testing Core Command Groups...")
        all_results['config'] = self.test_config_commands()
        all_results['auth'] = self.test_auth_commands()
        all_results['wallet'] = self.test_wallet_commands()
        all_results['blockchain'] = self.test_blockchain_commands()
        all_results['utility'] = self.test_utility_commands()
        
        return all_results
    
    def print_results_summary(self, results: Dict[str, Dict[str, CommandTestResult]]):
        """Print comprehensive results summary"""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE TEST RESULTS")
        print("="*80)
        
        total_tests = 0
        total_passed = 0
        total_failed = 0
        
        for category, tests in results.items():
            print(f"\n📂 {category.upper()} COMMANDS")
            print("-"*40)
            
            category_passed = 0
            category_total = len(tests)
            
            for test_name, result in tests.items():
                total_tests += 1
                if result.success:
                    total_passed += 1
                    category_passed += 1
                else:
                    total_failed += 1
                
                print(f"  {result}")
                if not result.success and result.error:
                    print(f"    Error: {result.error}")
            
            success_rate = (category_passed / category_total * 100) if category_total > 0 else 0
            print(f"\n  Category Success: {category_passed}/{category_total} ({success_rate:.1f}%)")
        
        # Overall summary
        print("\n" + "="*80)
        print("🎯 OVERALL SUMMARY")
        print("="*80)
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {total_passed}")
        print(f"❌ Failed: {total_failed}")
        
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"🎯 Success Rate: {overall_success_rate:.1f}%")
        
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: CLI is in excellent condition!")
        elif overall_success_rate >= 75:
            print("👍 GOOD: CLI is in good condition")
        elif overall_success_rate >= 50:
            print("⚠️  FAIR: CLI needs some attention")
        else:
            print("🚨 POOR: CLI needs immediate attention")
        
        return total_failed == 0


# Import necessary functions and classes
from .test_helpers import (
    MockConfig, MockApiResponse, TestEnvironment, 
    mock_api_responses, setup_test_mocks
)

# Mock API responses function that was missing
def mock_api_responses():
    """Common mock API responses for testing"""
    return {
        'blockchain_info': {
            'chain_id': 'ait-devnet',
            'height': 1000,
            'hash': '0x1234567890abcdef',
            'timestamp': '2026-01-01T00:00:00Z'
        },
        'blockchain_status': {
            'status': 'syncing',
            'height': 1000,
            'peers': 5,
            'sync_progress': 85.5
        },
        'wallet_balance': {
            'address': 'test-address',
            'balance': 1000.0,
            'unlocked': 800.0,
            'staked': 200.0
        },
        'node_info': {
            'id': 'test-node',
            'address': 'localhost:8006',
            'status': 'active',
            'chains': ['ait-devnet']
        }
    }
