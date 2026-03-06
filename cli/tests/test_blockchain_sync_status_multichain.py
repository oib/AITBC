#!/usr/bin/env python3
"""
Test multi-chain functionality for blockchain sync_status command
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from aitbc_cli.cli import cli


class TestBlockchainSyncStatusMultiChain:
    """Test blockchain sync_status multi-chain functionality"""
    
    def setup_method(self):
        """Setup test runner"""
        self.runner = CliRunner()
    
    def test_blockchain_sync_status_help(self):
        """Test blockchain sync_status help shows new options"""
        result = self.runner.invoke(cli, ['blockchain', 'sync-status', '--help'])
        success = result.exit_code == 0
        has_chain_option = '--chain-id' in result.output
        has_all_chains_option = '--all-chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain sync_status help: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_option else '❌'} --chain-id option: {'Available' if has_chain_option else 'Missing'}")
        print(f"    {'✅' if has_all_chains_option else '❌'} --all-chains option: {'Available' if has_all_chains_option else 'Missing'}")
        
        return success and has_chain_option and has_all_chains_option
    
    @patch('httpx.Client')
    def test_blockchain_sync_status_single_chain(self, mock_client):
        """Test blockchain sync_status for single chain"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"synced": True, "height": 1000, "peers": 5}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'sync-status', '--chain-id', 'ait-devnet'])
        success = result.exit_code == 0
        has_chain_id = 'ait-devnet' in result.output
        has_synced = 'synced' in result.output
        has_query_type = 'single_chain' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain sync_status single chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_chain_id else '❌'} chain ID in output: {'Present' if has_chain_id else 'Missing'}")
        print(f"    {'✅' if has_synced else '❌'} sync status: {'Present' if has_synced else 'Missing'}")
        print(f"    {'✅' if has_query_type else '❌'} query type: {'Present' if has_query_type else 'Missing'}")
        
        return success and has_chain_id and has_synced and has_query_type
    
    @patch('httpx.Client')
    def test_blockchain_sync_status_all_chains(self, mock_client):
        """Test blockchain sync_status across all chains"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"synced": True, "height": 1000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'sync-status', '--all-chains'])
        success = result.exit_code == 0
        has_multiple_chains = 'chains' in result.output
        has_total_chains = 'total_chains' in result.output
        has_available_chains = 'available_chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain sync_status all chains: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_multiple_chains else '❌'} multiple chains data: {'Present' if has_multiple_chains else 'Missing'}")
        print(f"    {'✅' if has_total_chains else '❌'} total chains count: {'Present' if has_total_chains else 'Missing'}")
        print(f"    {'✅' if has_available_chains else '❌'} available chains count: {'Present' if has_available_chains else 'Missing'}")
        
        return success and has_multiple_chains and has_total_chains and has_available_chains
    
    @patch('httpx.Client')
    def test_blockchain_sync_status_default_chain(self, mock_client):
        """Test blockchain sync_status uses default chain when none specified"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"synced": True, "height": 1000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'sync-status'])
        success = result.exit_code == 0
        has_default_chain = 'ait-devnet' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain sync_status default chain: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_default_chain else '❌'} default chain (ait-devnet): {'Used' if has_default_chain else 'Not used'}")
        
        return success and has_default_chain
    
    @patch('httpx.Client')
    def test_blockchain_sync_status_not_synced(self, mock_client):
        """Test blockchain sync_status when chain is not synced"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"synced": False, "height": 500, "target_height": 1000}
        
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.runner.invoke(cli, ['blockchain', 'sync-status', '--chain-id', 'ait-testnet'])
        success = result.exit_code == 0
        has_synced_false = '"synced": false' in result.output
        has_height_info = 'height' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain sync_status not synced: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_synced_false else '❌'} synced false: {'Present' if has_synced_false else 'Missing'}")
        print(f"    {'✅' if has_height_info else '❌'} height info: {'Present' if has_height_info else 'Missing'}")
        
        return success and has_synced_false and has_height_info
    
    @patch('httpx.Client')
    def test_blockchain_sync_status_partial_sync_all_chains(self, mock_client):
        """Test blockchain sync_status with some chains synced and some not"""
        def side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            if 'ait-devnet' in str(args[0]):
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"synced": True, "height": 1000}
            else:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"synced": False, "height": 500}
            return mock_resp
        
        mock_client.return_value.__enter__.return_value.get.side_effect = side_effect
        
        result = self.runner.invoke(cli, ['blockchain', 'sync-status', '--all-chains'])
        success = result.exit_code == 0
        has_available_chains = 'available_chains' in result.output
        has_chains_data = 'chains' in result.output
        
        print(f"    {'✅' if success else '❌'} blockchain sync_status partial sync: {'Working' if success else 'Failed'}")
        print(f"    {'✅' if has_available_chains else '❌'} available chains count: {'Present' if has_available_chains else 'Missing'}")
        print(f"    {'✅' if has_chains_data else '❌'} chains data: {'Present' if has_chains_data else 'Missing'}")
        
        return success and has_available_chains and has_chains_data


def run_blockchain_sync_status_multichain_tests():
    """Run all blockchain sync_status multi-chain tests"""
    print("🔗 Testing Blockchain Sync Status Multi-Chain Functionality")
    print("=" * 60)
    
    test_instance = TestBlockchainSyncStatusMultiChain()
    
    tests = [
        ("Help Options", test_instance.test_blockchain_sync_status_help),
        ("Single Chain Query", test_instance.test_blockchain_sync_status_single_chain),
        ("All Chains Query", test_instance.test_blockchain_sync_status_all_chains),
        ("Default Chain", test_instance.test_blockchain_sync_status_default_chain),
        ("Not Synced Chain", test_instance.test_blockchain_sync_status_not_synced),
        ("Partial Sync", test_instance.test_blockchain_sync_status_partial_sync_all_chains),
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
    print("📊 BLOCKCHAIN SYNC STATUS MULTI-CHAIN TEST SUMMARY")
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
    run_blockchain_sync_status_multichain_tests()
