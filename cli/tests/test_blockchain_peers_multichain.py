#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain peers command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainPeersMultiChain:
    """Test blockchain peers multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_peers_help(self):
        """Test blockchain peers help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'peers', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain peers help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_peers_single_chain(self, mock_client):
        """Test blockchain peers for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"peers": [{"id": "peer1", "address": "127.0.0.1:8001"}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'peers', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_peers = 'peers' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain peers single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_peers else '❌'} peers data: {'Present' if has_peers else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_peers and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_peers_all_chains(self, mock_client):
        """Test blockchain peers across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"peers": [{"id": "peer1"}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'peers', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_chains_with_peers = 'chains_with_peers' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain peers all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_chains_with_peers else '❌'} chains with peers: {'Present' if has_chains_with_peers else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_chains_with_peers
    
    @patch('httpx.Client')
    def test_blockchain_peers_default_chain(self, mock_client):
        """Test blockchain peers uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"peers": [{"id": "peer1"}]}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'peers'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain peers default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_peers_no_peers_available(self, mock_client):
        """Test blockchain peers when no P2P peers available"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "No peers endpoint"
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'peers', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_no_peers_message = 'No P2P peers available' in result.output
        has_available_false = '"available": false' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain peers no peers: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_no_peers_message else '❌'} no peers message: {'Present' if has_no_peers_message else 'Missing'}")
        print(f"    {'✅' if has_available_false else '❌'} available false: {'Present' if has_available_false else 'Missing'}")
        
        return success and has_no_peers_message and has_available_false
    
    @patch('httpx.Client')
    def test_blockchain_peers_partial_availability_all_chains(self, mock_client):
        """Test blockchain peers with some chains having peers and some not"""
        def side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            if 'ait-devnet' in str(args[0]):
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"peers": [{"id": "peer1"}]}
            else:
                mock_resp.status_code = 404
                mock_resp.text = "No peers endpoint"
            return mock_resp
        
        mock_client.return_value.__enter__.return_value.get.side_effect = side_effect
        
        result = self.runner.invoke(cli, ['blockchain', 'peers', '--all-chains'])
        success = result.exit_code == 0
        has_chains_with_peers = 'chains_with_peers' in result.output
        has_partial_availability = '1' in result.output  # Should have 1 chain with peers
        
        print(f"    {'✅' if success else '❌'} blockchain peers partial availability: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chains_with_peers else '❌'} chains with peers count: {'Present' if has_chains_with_peers else 'Missing'}")
        print(f"    {'✅' if has_partial_availability else '❌'} partial availability: {'Present' if has_partial_availability else 'Missing'}")
        
        return success and has_chains_with_peers and has_partial_availability


def run_blockchain_peers_multichain_tests():
    """Run all blockchain peers multi-chain tests"""
    print("🔗 Testing Blockchain Peers Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainPeersMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_peers_help),
        ("Single Chain Query", test_instance.test_blockchain_peers_single_chain),
        ("All Chains Query", test_instance.test_blockchain_peers_all_chains),
        ("Default Chain", test_instance.test_blockchain_peers_default_chain),
        ("No Peers Available", test_instance.test_blockchain_peers_no_peers_available),
        ("Partial Availability", test_instance.test_blockchain_peers_partial_availability_all_chains),
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
    print("📊 BLOCKCHAIN PEERS MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_peers_multichain_tests()
