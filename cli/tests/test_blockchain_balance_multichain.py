#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain balance command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainBalanceMultiChain:
    """Test blockchain balance multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_balance_help(self):
        """Test blockchain balance help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'balance', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain balance help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_balance_single_chain(self, mock_client):
        """Test blockchain balance for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"balance": 1000, "address": "test-address"}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'balance', '--address', 'test-address', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_balance = 'balance' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain balance single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_balance else '❌'} balance data: {'Present' if has_balance else 'Missing'}")
        
        return success and has_chain_id and has_balance
    
    @patch('httpx.Client')
    def test_blockchain_balance_all_chains(self, mock_client):
        """Test blockchain balance across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"balance": 1000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'balance', '--address', 'test-address', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain balance all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains
    
    @patch('httpx.Client')
    def test_blockchain_balance_default_chain(self, mock_client):
        """Test blockchain balance uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"balance": 1000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'balance', '--address', 'test-address'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain balance default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_balance_error_handling(self, mock_client):
        """Test blockchain balance error handling"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Address not found"
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'balance', '--address', 'invalid-address'])
        success = result.exit_code != 0  # Should fail
        has_error = 'Failed to get balance' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain balance error handling: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_error else '❌'} error message: {'Present' if has_error else 'Missing'}")
        
        return success and has_error


def run_blockchain_balance_multichain_tests():
    """Run all blockchain balance multi-chain tests"""
    print("🔗 Testing Blockchain Balance Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainBalanceMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_balance_help),
        ("Single Chain Query", test_instance.test_blockchain_balance_single_chain),
        ("All Chains Query", test_instance.test_blockchain_balance_all_chains),
        ("Default Chain", test_instance.test_blockchain_balance_default_chain),
        ("Error Handling", test_instance.test_blockchain_balance_error_handling),
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
    print("📊 BLOCKCHAIN BALANCE MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_balance_multichain_tests()
