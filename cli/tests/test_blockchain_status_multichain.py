#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain status command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainStatusMultiChain:
    """Test blockchain status multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_status_help(self):
        """Test blockchain status help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'status', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain status help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_status_single_chain(self, mock_client):
        """Test blockchain status for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "version": "1.0.0"}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'status', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_healthy = 'healthy' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain status single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_healthy else '❌'} healthy status: {'Present' if has_healthy else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_healthy and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_status_all_chains(self, mock_client):
        """Test blockchain status across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "version": "1.0.0"}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'status', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_healthy_chains = 'healthy_chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain status all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_healthy_chains else '❌'} healthy chains count: {'Present' if has_healthy_chains else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_healthy_chains
    
    @patch('httpx.Client')
    def test_blockchain_status_default_chain(self, mock_client):
        """Test blockchain status uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'status'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain status default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_status_error_handling(self, mock_client):
        """Test blockchain status error handling"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'status', '--chain-id', 'invalid-chain'])
        success = result.exit_code == 0  # Should succeed but show error in output
        has_error = 'HTTP 500' in result.output
        has_healthy_false = '"healthy": false' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain status error handling: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_error else '❌'} error message: {'Present' if has_error else 'Missing'}")
        print(f"    {'✅' if has_healthy_false else '❌'} healthy false: {'Present' if has_healthy_false else 'Missing'}")
        
        return success and has_error and has_healthy_false
    
    @patch('httpx.Client')
    def test_blockchain_status_partial_success_all_chains(self, mock_client):
        """Test blockchain status with some chains healthy and some not"""
        def side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            if 'ait-devnet' in str(args[0]):
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"status": "healthy"}
            else:
                mock_resp.status_code = 503
                mock_resp.text = "Service unavailable"
            return mock_resp
        
        mock_client.return_value.__enter__.return_value.get.side_effect = side_effect
        
        result = self.runner.invoke(cli, ['blockchain', 'status', '--all-chains'])
        success = result.exit_code == 0
        has_healthy_chains = 'healthy_chains' in result.output
        has_partial_health = '1' in result.output  # Should have 1 healthy chain
        
        print(f"    {'✅' if success else '❌'} blockchain status partial success: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_healthy_chains else '❌'} healthy chains count: {'Present' if has_healthy_chains else 'Missing'}")
        print(f"    {'✅' if has_partial_health else '❌'} partial health count: {'Present' if has_partial_health else 'Missing'}")
        
        return success and has_healthy_chains and has_partial_health


def run_blockchain_status_multichain_tests():
    """Run all blockchain status multi-chain tests"""
    print("🔗 Testing Blockchain Status Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainStatusMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_status_help),
        ("Single Chain Query", test_instance.test_blockchain_status_single_chain),
        ("All Chains Query", test_instance.test_blockchain_status_all_chains),
        ("Default Chain", test_instance.test_blockchain_status_default_chain),
        ("Error Handling", test_instance.test_blockchain_status_error_handling),
        ("Partial Success", test_instance.test_blockchain_status_partial_success_all_chains),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"    ❌ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total) * 100 if total > 0 else 0
    
    print("\n" + "=" * 60)
    print("📊 BLOCKCHAIN STATUS MULTI-CHAIN TEST SUMMARY")
    print("=" * 60)
    print(f"Tests Passed: {passed}/{total}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("✅ Multi-chain functionality is working well!")
    elif success_rate >= 60:
        print("⚠️ Multi-chain functionality has some issues")
    else:
        print("❌ Multi-chain functionality needs significant work")
    
    return success_rate


if __name__ == "__main__":
    run_blockchain_status_multichain_tests()
