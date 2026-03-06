#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain blocks command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainBlocksMultiChain:
    """Test blockchain blocks multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_blocks_help(self):
        """Test blockchain blocks help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'blocks', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain blocks help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_blocks_single_chain(self, mock_client):
        """Test blockchain blocks for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": [{"height": 100, "hash": "0x123"}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'blocks', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_blocks = 'blocks' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain blocks single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_blocks else '❌'} blocks data: {'Present' if has_blocks else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_blocks and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_blocks_all_chains(self, mock_client):
        """Test blockchain blocks across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": [{"height": 100}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'blocks', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_successful_queries = 'successful_queries' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain blocks all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_successful_queries else '❌'} successful queries: {'Present' if has_successful_queries else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_successful_queries
    
    @patch('httpx.Client')
    def test_blockchain_blocks_default_chain(self, mock_client):
        """Test blockchain blocks uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": [{"height": 100}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'blocks'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain blocks default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_blocks_error_handling(self, mock_client):
        """Test blockchain blocks error handling"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Blocks not found"
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'blocks', '--chain-id', 'invalid-chain'])
        success = result.exit_code != 0  # Should fail
        has_error = 'Failed to get blocks' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain blocks error handling: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_error else '❌'} error message: {'Present' if has_error else 'Missing'}")
        
        return success and has_error


def run_blockchain_blocks_multichain_tests():
    """Run all blockchain blocks multi-chain tests"""
    print("🔗 Testing Blockchain Blocks Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainBlocksMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_blocks_help),
        ("Single Chain Query", test_instance.test_blockchain_blocks_single_chain),
        ("All Chains Query", test_instance.test_blockchain_blocks_all_chains),
        ("Default Chain", test_instance.test_blockchain_blocks_default_chain),
        ("Error Handling", test_instance.test_blockchain_blocks_error_handling),
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
    print("📊 BLOCKCHAIN BLOCKS MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_blocks_multichain_tests()
