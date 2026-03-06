#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain validators command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainValidatorsMultiChain:
    """Test blockchain validators multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_validators_help(self):
        """Test blockchain validators help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'validators', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain validators help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_validators_single_chain(self, mock_client):
        """Test blockchain validators for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"validators": [{"address": "0x123", "stake": 1000}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'validators', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_validators = 'validators' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain validators single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_validators else '❌'} validators data: {'Present' if has_validators else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_validators and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_validators_all_chains(self, mock_client):
        """Test blockchain validators across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"validators": [{"address": "0x123", "stake": 1000}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'validators', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_chains_with_validators = 'chains_with_validators' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain validators all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_chains_with_validators else '❌'} chains with validators: {'Present' if has_chains_with_validators else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_chains_with_validators
    
    @patch('httpx.Client')
    def test_blockchain_validators_default_chain(self, mock_client):
        """Test blockchain validators uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"validators": [{"address": "0x123"}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'validators'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain validators default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_validators_with_stake_info(self, mock_client):
        """Test blockchain validators with detailed stake information"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "validators": [
                {"address": "0x123", "stake": 1000, "commission": 0.1, "status": "active"},
                {"address": "0x456", "stake": 2000, "commission": 0.05, "status": "active"}
            ]
        }
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'validators', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_stake = 'stake' in result.output
        has_commission = 'commission' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain validators with stake: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_stake else '❌'} stake info: {'Present' if has_stake else 'Missing'}")
        print(f"    {'✅' if has_commission else '❌'} commission info: {'Present' if has_commission else 'Missing'}")
        
        return success and has_stake and has_commission
    
    @patch('httpx.Client')
    def test_blockchain_validators_partial_availability_all_chains(self, mock_client):
        """Test blockchain validators with some chains available and some not"""
        def side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            if 'ait-devnet' in str(args[0]):
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"validators": [{"address": "0x123"}]}
            else:
                mock_resp.status_code = 503
                mock_resp.text = "Validators service unavailable"
            return mock_resp
        
        mock_client.return_value.__enter__.return_value.get.side_effect = side_effect
        
        result = self.runner.invoke(cli, ['blockchain', 'validators', '--all-chains'])
        success = result.exit_code == 0
        has_chains_with_validators = 'chains_with_validators' in result.output
        has_error_info = 'HTTP 503' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain validators partial availability: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chains_with_validators else '❌'} chains with validators count: {'Present' if has_chains_with_validators else 'Missing'}")
        print(f"    {'✅' if has_error_info else '❌'} error info: {'Present' if has_error_info else 'Missing'}")
        
        return success and has_chains_with_validators and has_error_info


def run_blockchain_validators_multichain_tests():
    """Run all blockchain validators multi-chain tests"""
    print("🔗 Testing Blockchain Validators Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainValidatorsMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_validators_help),
        ("Single Chain Query", test_instance.test_blockchain_validators_single_chain),
        ("All Chains Query", test_instance.test_blockchain_validators_all_chains),
        ("Default Chain", test_instance.test_blockchain_validators_default_chain),
        ("Stake Information", test_instance.test_blockchain_validators_with_stake_info),
        ("Partial Availability", test_instance.test_blockchain_validators_partial_availability_all_chains),
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
    print("📊 BLOCKCHAIN VALIDATORS MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_validators_multichain_tests()
