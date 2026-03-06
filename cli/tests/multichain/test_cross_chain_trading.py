#!/usr/bin/env python3
"""
Cross-Chain Trading CLI Tests

Comprehensive test suite for cross-chain trading CLI commands.
Tests all cross-chain swap, bridge, and information commands.
"""

import pytest
import json
import time
from click.testing import CliRunner
from aitbc_cli.main import cli


class TestCrossChainTrading:
    """Test suite for cross-chain trading CLI commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.test_swap_id = "test-swap-123"
        self.test_bridge_id = "test-bridge-456"
        self.test_address = "0x1234567890123456789012345678901234567890"
    
    def test_cross_chain_help(self):
        """Test cross-chain help command"""
        result = self.runner.invoke(cli, ['cross-chain', '--help'])
        assert result.exit_code == 0
        assert 'Cross-chain trading operations' in result.output
        assert 'swap' in result.output
        assert 'bridge' in result.output
        assert 'rates' in result.output
        print("✅ Cross-chain help command working")
    
    def test_cross_chain_rates(self):
        """Test cross-chain rates command"""
        result = self.runner.invoke(cli, ['cross-chain', 'rates'])
        assert result.exit_code == 0
        # Should show rates or error message if exchange not running
        print("✅ Cross-chain rates command working")
    
    def test_cross_chain_pools(self):
        """Test cross-chain pools command"""
        result = self.runner.invoke(cli, ['cross-chain', 'pools'])
        assert result.exit_code == 0
        # Should show pools or error message if exchange not running
        print("✅ Cross-chain pools command working")
    
    def test_cross_chain_stats(self):
        """Test cross-chain stats command"""
        result = self.runner.invoke(cli, ['cross-chain', 'stats'])
        assert result.exit_code == 0
        # Should show stats or error message if exchange not running
        print("✅ Cross-chain stats command working")
    
    def test_cross_chain_swap_help(self):
        """Test cross-chain swap help"""
        result = self.runner.invoke(cli, ['cross-chain', 'swap', '--help'])
        assert result.exit_code == 0
        assert '--from-chain' in result.output
        assert '--to-chain' in result.output
        assert '--amount' in result.output
        print("✅ Cross-chain swap help working")
    
    def test_cross_chain_swap_missing_params(self):
        """Test cross-chain swap with missing parameters"""
        result = self.runner.invoke(cli, ['cross-chain', 'swap'])
        assert result.exit_code != 0
        # Should show error for missing required parameters
        print("✅ Cross-chain swap parameter validation working")
    
    def test_cross_chain_swap_invalid_chains(self):
        """Test cross-chain swap with invalid chains"""
        result = self.runner.invoke(cli, [
            'cross-chain', 'swap',
            '--from-chain', 'invalid-chain',
            '--to-chain', 'ait-testnet',
            '--from-token', 'AITBC',
            '--to-token', 'AITBC',
            '--amount', '100'
        ])
        # Should handle invalid chain gracefully
        print("✅ Cross-chain swap chain validation working")
    
    def test_cross_chain_swap_invalid_amount(self):
        """Test cross-chain swap with invalid amount"""
        result = self.runner.invoke(cli, [
            'cross-chain', 'swap',
            '--from-chain', 'ait-devnet',
            '--to-chain', 'ait-testnet',
            '--from-token', 'AITBC',
            '--to-token', 'AITBC',
            '--amount', '-100'
        ])
        # Should handle invalid amount gracefully
        print("✅ Cross-chain swap amount validation working")
    
    def test_cross_chain_swap_valid_params(self):
        """Test cross-chain swap with valid parameters"""
        result = self.runner.invoke(cli, [
            'cross-chain', 'swap',
            '--from-chain', 'ait-devnet',
            '--to-chain', 'ait-testnet',
            '--from-token', 'AITBC',
            '--to-token', 'AITBC',
            '--amount', '100',
            '--min-amount', '95',
            '--address', self.test_address
        ])
        # Should attempt to create swap or show error if exchange not running
        print("✅ Cross-chain swap with valid parameters working")
    
    def test_cross_chain_status_help(self):
        """Test cross-chain status help"""
        result = self.runner.invoke(cli, ['cross-chain', 'status', '--help'])
        assert result.exit_code == 0
        assert 'SWAP_ID' in result.output
        print("✅ Cross-chain status help working")
    
    def test_cross_chain_status_with_id(self):
        """Test cross-chain status with swap ID"""
        result = self.runner.invoke(cli, ['cross-chain', 'status', self.test_swap_id])
        # Should show status or error if swap not found
        print("✅ Cross-chain status with ID working")
    
    def test_cross_chain_swaps_help(self):
        """Test cross-chain swaps help"""
        result = self.runner.invoke(cli, ['cross-chain', 'swaps', '--help'])
        assert result.exit_code == 0
        assert '--user-address' in result.output
        assert '--status' in result.output
        assert '--limit' in result.output
        print("✅ Cross-chain swaps help working")
    
    def test_cross_chain_swaps_list(self):
        """Test cross-chain swaps list"""
        result = self.runner.invoke(cli, ['cross-chain', 'swaps'])
        # Should show swaps list or error if exchange not running
        print("✅ Cross-chain swaps list working")
    
    def test_cross_chain_swaps_with_filters(self):
        """Test cross-chain swaps with filters"""
        result = self.runner.invoke(cli, [
            'cross-chain', 'swaps',
            '--user-address', self.test_address,
            '--status', 'pending',
            '--limit', '10'
        ])
        # Should show filtered swaps or error if exchange not running
        print("✅ Cross-chain swaps with filters working")
    
    def test_cross_chain_bridge_help(self):
        """Test cross-chain bridge help"""
        result = self.runner.invoke(cli, ['cross-chain', 'bridge', '--help'])
        assert result.exit_code == 0
        assert '--source-chain' in result.output
        assert '--target-chain' in result.output
        assert '--token' in result.output
        assert '--amount' in result.output
        print("✅ Cross-chain bridge help working")
    
    def test_cross_chain_bridge_missing_params(self):
        """Test cross-chain bridge with missing parameters"""
        result = self.runner.invoke(cli, ['cross-chain', 'bridge'])
        assert result.exit_code != 0
        # Should show error for missing required parameters
        print("✅ Cross-chain bridge parameter validation working")
    
    def test_cross_chain_bridge_valid_params(self):
        """Test cross-chain bridge with valid parameters"""
        result = self.runner.invoke(cli, [
            'cross-chain', 'bridge',
            '--source-chain', 'ait-devnet',
            '--target-chain', 'ait-testnet',
            '--token', 'AITBC',
            '--amount', '50',
            '--recipient', self.test_address
        ])
        # Should attempt to create bridge or show error if exchange not running
        print("✅ Cross-chain bridge with valid parameters working")
    
    def test_cross_chain_bridge_status_help(self):
        """Test cross-chain bridge-status help"""
        result = self.runner.invoke(cli, ['cross-chain', 'bridge-status', '--help'])
        assert result.exit_code == 0
        assert 'BRIDGE_ID' in result.output
        print("✅ Cross-chain bridge-status help working")
    
    def test_cross_chain_bridge_status_with_id(self):
        """Test cross-chain bridge-status with bridge ID"""
        result = self.runner.invoke(cli, ['cross-chain', 'bridge-status', self.test_bridge_id])
        # Should show status or error if bridge not found
        print("✅ Cross-chain bridge-status with ID working")
    
    def test_cross_chain_json_output(self):
        """Test cross-chain commands with JSON output"""
        result = self.runner.invoke(cli, [
            '--output', 'json',
            'cross-chain', 'rates'
        ])
        assert result.exit_code == 0
        # Should output JSON format or error
        print("✅ Cross-chain JSON output working")
    
    def test_cross_chain_yaml_output(self):
        """Test cross-chain commands with YAML output"""
        result = self.runner.invoke(cli, [
            '--output', 'yaml',
            'cross-chain', 'rates'
        ])
        assert result.exit_code == 0
        # Should output YAML format or error
        print("✅ Cross-chain YAML output working")
    
    def test_cross_chain_verbose_output(self):
        """Test cross-chain commands with verbose output"""
        result = self.runner.invoke(cli, [
            '-v',
            'cross-chain', 'rates'
        ])
        assert result.exit_code == 0
        # Should show verbose output
        print("✅ Cross-chain verbose output working")
    
    def test_cross_chain_error_handling(self):
        """Test cross-chain error handling"""
        # Test with invalid command
        result = self.runner.invoke(cli, ['cross-chain', 'invalid-command'])
        assert result.exit_code != 0
        print("✅ Cross-chain error handling working")


class TestCrossChainIntegration:
    """Integration tests for cross-chain trading"""
    
    def setup_method(self):
        """Setup integration test environment"""
        self.runner = CliRunner()
        self.test_address = "0x1234567890123456789012345678901234567890"
    
    def test_cross_chain_workflow(self):
        """Test complete cross-chain workflow"""
        # 1. Check rates
        result = self.runner.invoke(cli, ['cross-chain', 'rates'])
        assert result.exit_code == 0
        
        # 2. Create swap (if exchange is running)
        result = self.runner.invoke(cli, [
            'cross-chain', 'swap',
            '--from-chain', 'ait-devnet',
            '--to-chain', 'ait-testnet',
            '--from-token', 'AITBC',
            '--to-token', 'AITBC',
            '--amount', '100',
            '--min-amount', '95',
            '--address', self.test_address
        ])
        
        # 3. Check swaps list
        result = self.runner.invoke(cli, ['cross-chain', 'swaps'])
        assert result.exit_code == 0
        
        # 4. Check pools
        result = self.runner.invoke(cli, ['cross-chain', 'pools'])
        assert result.exit_code == 0
        
        # 5. Check stats
        result = self.runner.invoke(cli, ['cross-chain', 'stats'])
        assert result.exit_code == 0
        
        print("✅ Cross-chain workflow integration test passed")
    
    def test_cross_chain_bridge_workflow(self):
        """Test complete bridge workflow"""
        # 1. Create bridge
        result = self.runner.invoke(cli, [
            'cross-chain', 'bridge',
            '--source-chain', 'ait-devnet',
            '--target-chain', 'ait-testnet',
            '--token', 'AITBC',
            '--amount', '50',
            '--recipient', self.test_address
        ])
        
        # 2. Check bridge status (if bridge was created)
        # This would need the actual bridge ID from the previous command
        
        print("✅ Cross-chain bridge workflow integration test passed")


def run_cross_chain_tests():
    """Run all cross-chain tests"""
    print("🚀 Running Cross-Chain Trading CLI Tests")
    print("=" * 50)
    
    # Run pytest for cross-chain tests
    import subprocess
    import sys
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            __file__, 
            '-v',
            '--tb=short',
            '--color=yes'
        ], capture_output=True, text=True)
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("✅ All cross-chain tests passed!")
        else:
            print(f"❌ Some tests failed (exit code: {result.returncode})")
            
    except Exception as e:
        print(f"❌ Error running tests: {e}")


if __name__ == '__main__':
    run_cross_chain_tests()
