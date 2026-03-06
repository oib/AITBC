#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain supply command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainSupplyMultiChain:
    """Test blockchain supply multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_supply_help(self):
        """Test blockchain supply help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'supply', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain supply help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_supply_single_chain(self, mock_client):
        """Test blockchain supply for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_supply": 1000000, "circulating": 800000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'supply', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_supply = 'supply' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain supply single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_supply else '❌'} supply data: {'Present' if has_supply else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_supply and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_supply_all_chains(self, mock_client):
        """Test blockchain supply across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_supply": 1000000, "circulating": 800000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'supply', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_chains_with_supply = 'chains_with_supply' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain supply all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_chains_with_supply else '❌'} chains with supply: {'Present' if has_chains_with_supply else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_chains_with_supply
    
    @patch('httpx.Client')
    def test_blockchain_supply_default_chain(self, mock_client):
        """Test blockchain supply uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_supply": 1000000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'supply'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain supply default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_supply_with_detailed_data(self, mock_client):
        """Test blockchain supply with detailed supply data"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_supply": 1000000,
            "circulating": 800000,
            "locked": 150000,
            "staking": 50000
        }
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'supply', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_circulating = 'circulating' in result.output
        has_locked = 'locked' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain supply detailed data: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_circulating else '❌'} circulating supply: {'Present' if has_circulating else 'Missing'}")
        print(f"    {'✅' if has_locked else '❌'} locked supply: {'Present' if has_locked else 'Missing'}")
        
        return success and has_circulating and has_locked
    
    @patch('httpx.Client')
    def test_blockchain_supply_partial_availability_all_chains(self, mock_client):
        """Test blockchain supply with some chains available and some not"""
        def side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            if 'ait-devnet' in str(args[0]):
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"total_supply": 1000000}
            else:
                mock_resp.status_code = 503
                mock_resp.text = "Service unavailable"
            return mock_resp
        
        mock_client.return_value.__enter__.return_value.get.side_effect = side_effect
        
        result = self.runner.invoke(cli, ['blockchain', 'supply', '--all-chains'])
        success = result.exit_code == 0
        has_chains_with_supply = 'chains_with_supply' in result.output
        has_error_info = 'HTTP 503' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain supply partial availability: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chains_with_supply else '❌'} chains with supply count: {'Present' if has_chains_with_supply else 'Missing'}")
        print(f"    {'✅' if has_error_info else '❌'} error info: {'Present' if has_error_info else 'Missing'}")
        
        return success and has_chains_with_supply and has_error_info


def run_blockchain_supply_multichain_tests():
    """Run all blockchain supply multi-chain tests"""
    print("🔗 Testing Blockchain Supply Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainSupplyMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_supply_help),
        ("Single Chain Query", test_instance.test_blockchain_supply_single_chain),
        ("All Chains Query", test_instance.test_blockchain_supply_all_chains),
        ("Default Chain", test_instance.test_blockchain_supply_default_chain),
        ("Detailed Supply Data", test_instance.test_blockchain_supply_with_detailed_data),
        ("Partial Availability", test_instance.test_blockchain_supply_partial_availability_all_chains),
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
    print("📊 BLOCKCHAIN SUPPLY MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_supply_multichain_tests()
