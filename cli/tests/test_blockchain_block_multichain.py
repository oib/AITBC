#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain block command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainBlockMultiChain:
    """Test blockchain block multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_block_help(self):
        """Test blockchain block help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'block', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain block help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_block_single_chain(self, mock_client):
        """Test blockchain block for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 100}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'block', '0x123', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_block_data = 'block_data' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain block single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_block_data else '❌'} block data: {'Present' if has_block_data else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_block_data and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_block_all_chains(self, mock_client):
        """Test blockchain block across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 100}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'block', '0x123', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_successful_searches = 'successful_searches' in result.output
        has_found_in_chains = 'found_in_chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain block all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_successful_searches else '❌'} successful searches: {'Present' if has_successful_searches else 'Missing'}")
        print(f"    {'✅' if has_found_in_chains else '❌'} found in chains: {'Present' if has_found_in_chains else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_successful_searches and has_found_in_chains
    
    @patch('httpx.Client')
    def test_blockchain_block_default_chain(self, mock_client):
        """Test blockchain block uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 100}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'block', '0x123'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain block default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_block_by_height(self, mock_client):
        """Test blockchain block by height (numeric hash)"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hash": "0x123", "height": 100}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'block', '100', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_height = 'height' in result.output
        has_query_type = 'single_chain_by_height' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain block by height: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_height else '❌'} height in output: {'Present' if has_height else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type by height: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_height and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_block_error_handling(self, mock_client):
        """Test blockchain block error handling"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Block not found"
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'block', '0xinvalid', '--chain-id', 'invalid-chain'])
        success = result.exit_code != 0  # Should fail
        has_error = 'Block not found' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain block error handling: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_error else '❌'} error message: {'Present' if has_error else 'Missing'}")
        
        return success and has_error


def run_blockchain_block_multichain_tests():
    """Run all blockchain block multi-chain tests"""
    print("🔗 Testing Blockchain Block Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainBlockMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_block_help),
        ("Single Chain Query", test_instance.test_blockchain_block_single_chain),
        ("All Chains Query", test_instance.test_blockchain_block_all_chains),
        ("Default Chain", test_instance.test_blockchain_block_default_chain),
        ("Block by Height", test_instance.test_blockchain_block_by_height),
        ("Error Handling", test_instance.test_blockchain_block_error_handling),
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
    print("📊 BLOCKCHAIN BLOCK MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_block_multichain_tests()
