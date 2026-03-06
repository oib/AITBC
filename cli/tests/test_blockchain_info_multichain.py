#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain info command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainInfoMultiChain:
    """Test blockchain info multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_info_help(self):
        """Test blockchain info help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'info', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain info help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_info_single_chain(self, mock_client):
        """Test blockchain info for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 1000, "timestamp": 1234567890}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'info', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_height = 'height' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain info single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_height else '❌'} height info: {'Present' if has_height else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_height and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_info_all_chains(self, mock_client):
        """Test blockchain info across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 1000, "timestamp": 1234567890}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'info', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_available_chains = 'available_chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain info all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_available_chains else '❌'} available chains count: {'Present' if has_available_chains else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_available_chains
    
    @patch('httpx.Client')
    def test_blockchain_info_default_chain(self, mock_client):
        """Test blockchain info uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 1000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'info'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain info default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_info_with_transactions(self, mock_client):
        """Test blockchain info with transaction count"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 1000, "tx_count": 25}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'info', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_tx_count = 'transactions_in_block' in result.output
        has_status_active = '"status": "active"' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain info with transactions: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_tx_count else '❌'} transaction count: {'Present' if has_tx_count else 'Missing'}")
        print(f"    {'✅' if has_status_active else '❌'} active status: {'Present' if has_status_active else 'Missing'}")
        
        return success and has_tx_count and has_status_active
    
    @patch('httpx.Client')
    def test_blockchain_info_partial_availability_all_chains(self, mock_client):
        """Test blockchain info with some chains available and some not"""
        def side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            if 'ait-devnet' in str(args[0]):
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"hash": "0x123", "height": 1000}
            else:
                mock_resp.status_code = 404
                mock_resp.text = "Chain not found"
            return mock_resp
        
        mock_client.return_value.__enter__.return_value.get.side_effect = side_effect
        
        result = self.runner.invoke(cli, ['blockchain', 'info', '--all-chains'])
        success = result.exit_code == 0
        has_available_chains = 'available_chains' in result.output
        has_error_info = 'HTTP 404' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain info partial availability: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_available_chains else '❌'} available chains count: {'Present' if has_available_chains else 'Missing'}")
        print(f"    {'✅' if has_error_info else '❌'} error info: {'Present' if has_error_info else 'Missing'}")
        
        return success and has_available_chains and has_error_info


def run_blockchain_info_multichain_tests():
    """Run all blockchain info multi-chain tests"""
    print("🔗 Testing Blockchain Info Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainInfoMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_info_help),
        ("Single Chain Query", test_instance.test_blockchain_info_single_chain),
        ("All Chains Query", test_instance.test_blockchain_info_all_chains),
        ("Default Chain", test_instance.test_blockchain_info_default_chain),
        ("Transaction Count", test_instance.test_blockchain_info_with_transactions),
        ("Partial Availability", test_instance.test_blockchain_info_partial_availability_all_chains),
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
    print("📊 BLOCKCHAIN INFO MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_info_multichain_tests()
