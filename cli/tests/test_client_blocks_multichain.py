#!/usr/bin/env python3
"""
Test multi-chain functionality for client blocks command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestClientBlocksMultiChain:
    """Test client blocks multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_client_blocks_help(self):
        """Test client blocks help shows new option"""
        result = self.runner.invoke(cli, ['client', 'blocks', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        
        print(f"    {'✅' if success else '❌'} client blocks help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        
        return success and has_chain_option
    
    @patch('httpx.Client')
    def test_client_blocks_single_chain(self, mock_client):
        """Test client blocks for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": [{"height": 100, "hash": "0x123"}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['client', 'blocks', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_blocks = 'blocks' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} client blocks single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_blocks else '❌'} blocks data: {'Present' if has_blocks else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_blocks and has_query_type
    
    @patch('httpx.Client')
    def test_client_blocks_default_chain(self, mock_client):
        """Test client blocks uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": [{"height": 100}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['client', 'blocks'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} client blocks default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_client_blocks_with_limit(self, mock_client):
        """Test client blocks with limit parameter"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": [{"height": 100}, {"height": 99}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['client', 'blocks', '--chain-id', 'ait-devnet', '--limit', 5])
        success = result.exit_code == 0
        has_limit = 'limit' in result.output
        has_chain_id = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} client blocks with limit: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_limit else '❌'} limit in output: {'Present' if has_limit else 'Missing'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        
        return success and has_limit and has_chain_id
    
    @patch('httpx.Client')
    def test_client_blocks_error_handling(self, mock_client):
        """Test client blocks error handling"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Blocks not found"
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['client', 'blocks', '--chain-id', 'invalid-chain'])
        success = result.exit_code != 0  # Should fail and exit
        has_error = 'Failed to get blocks' in result.output
        has_chain_specified = 'invalid-chain' in result.output
        
        print(f"    {'✅' if success else '❌'} client blocks error handling: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_error else '❌'} error message: {'Present' if has_error else 'Missing'}")
        print(f"    {'✅' if has_chain_specified else '❌'} chain specified in error: {'Present' if has_chain_specified else 'Missing'}")
        
        return success and has_error and has_chain_specified
    
    @patch('httpx.Client')
    def test_client_blocks_different_chains(self, mock_client):
        """Test client blocks with different chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blocks": [{"height": 100, "chain": "testnet"}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['client', 'blocks', '--chain-id', 'ait-testnet', '--limit', 3])
        success = result.exit_code == 0
        has_testnet = 'ait-testnet' in result.output
        has_limit_3 = 'limit' in result.output and '3' in result.output
        
        print(f"    {'✅' if success else '❌'} client blocks different chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_testnet else '❌'} testnet chain: {'Present' if has_testnet else 'Missing'}")
        print(f"    {'✅' if has_limit_3 else '❌'} limit 3: {'Present' if has_limit_3 else 'Missing'}")
        
        return success and has_testnet and has_limit_3


def run_client_blocks_multichain_tests():
    """Run all client blocks multi-chain tests"""
    print("🔗 Testing Client Blocks Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestClientBlocksMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_client_blocks_help),
        ("Single Chain Query", test_instance.test_client_blocks_single_chain),
        ("Default Chain", test_instance.test_client_blocks_default_chain),
        ("With Limit", test_instance.test_client_blocks_with_limit),
        ("Error Handling", test_instance.test_client_blocks_error_handling),
        ("Different Chains", test_instance.test_client_blocks_different_chains),
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
    print("📊 CLIENT BLOCKS MULTI-CHAIN TEST SUMMARY")
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
    run_client_blocks_multichain_tests()
