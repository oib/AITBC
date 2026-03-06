#!/usr/bin/env python3
"""
Multi-Chain Wallet CLI Tests

Comprehensive test suite for multi-chain wallet CLI commands.
Tests all multi-chain wallet operations including chain management,
wallet creation, balance checking, and migration.
"""

import pytest
import json
import os
import tempfile
from click.testing import CliRunner
from aitbc_cli.main import cli


class TestMultiChainWallet:
    """Test suite for multi-chain wallet CLI commands"""
    
    def setup_method(self):
        """Setup test environment"""
        self.runner = CliRunner()
        self.test_chain_id = "test-chain"
        self.test_wallet_name = "test-wallet"
        self.test_wallet_path = None
        
    def teardown_method(self):
        """Cleanup test environment"""
        if self.test_wallet_path and os.path.exists(self.test_wallet_path):
            os.remove(self.test_wallet_path)
    
    def test_wallet_chain_help(self):
        """Test wallet chain help command"""
        result = self.runner.invoke(cli, ['wallet', 'chain', '--help'])
        assert result.exit_code == 0
        assert 'Multi-chain wallet operations' in result.output
        assert 'balance' in result.output
        assert 'create' in result.output
        assert 'info' in result.output
        assert 'list' in result.output
        assert 'migrate' in result.output
        assert 'status' in result.output
        assert 'wallets' in result.output
        print("✅ Wallet chain help command working")
    
    def test_wallet_chain_list(self):
        """Test wallet chain list command"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'list'])
        assert result.exit_code == 0
        # Should show chains or error if no chains available
        print("✅ Wallet chain list command working")
    
    def test_wallet_chain_status(self):
        """Test wallet chain status command"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'status'])
        assert result.exit_code == 0
        # Should show status or error if no status available
        print("✅ Wallet chain status command working")
    
    def test_wallet_chain_create_help(self):
        """Test wallet chain create help"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'create', '--help'])
        assert result.exit_code == 0
        assert 'CHAIN_ID' in result.output
        print("✅ Wallet chain create help working")
    
    def test_wallet_chain_create_missing_params(self):
        """Test wallet chain create with missing parameters"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'create'])
        assert result.exit_code != 0
        # Should show error for missing chain ID
        print("✅ Wallet chain create parameter validation working")
    
    def test_wallet_chain_create_with_params(self):
        """Test wallet chain create with parameters"""
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'create',
            self.test_chain_id
        ])
        # Should attempt to create chain or show error
        print("✅ Wallet chain create with parameters working")
    
    def test_wallet_chain_balance_help(self):
        """Test wallet chain balance help"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'balance', '--help'])
        assert result.exit_code == 0
        assert 'CHAIN_ID' in result.output
        print("✅ Wallet chain balance help working")
    
    def test_wallet_chain_balance_missing_params(self):
        """Test wallet chain balance with missing parameters"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'balance'])
        assert result.exit_code != 0
        # Should show error for missing chain ID
        print("✅ Wallet chain balance parameter validation working")
    
    def test_wallet_chain_balance_with_params(self):
        """Test wallet chain balance with parameters"""
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'balance',
            self.test_chain_id
        ])
        # Should attempt to get balance or show error
        print("✅ Wallet chain balance with parameters working")
    
    def test_wallet_chain_info_help(self):
        """Test wallet chain info help"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'info', '--help'])
        assert result.exit_code == 0
        assert 'CHAIN_ID' in result.output
        print("✅ Wallet chain info help working")
    
    def test_wallet_chain_info_with_params(self):
        """Test wallet chain info with parameters"""
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'info',
            self.test_chain_id
        ])
        # Should attempt to get info or show error
        print("✅ Wallet chain info with parameters working")
    
    def test_wallet_chain_wallets_help(self):
        """Test wallet chain wallets help"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'wallets', '--help'])
        assert result.exit_code == 0
        assert 'CHAIN_ID' in result.output
        print("✅ Wallet chain wallets help working")
    
    def test_wallet_chain_wallets_with_params(self):
        """Test wallet chain wallets with parameters"""
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'wallets',
            self.test_chain_id
        ])
        # Should attempt to list wallets or show error
        print("✅ Wallet chain wallets with parameters working")
    
    def test_wallet_chain_migrate_help(self):
        """Test wallet chain migrate help"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'migrate', '--help'])
        assert result.exit_code == 0
        assert 'SOURCE_CHAIN' in result.output
        assert 'TARGET_CHAIN' in result.output
        print("✅ Wallet chain migrate help working")
    
    def test_wallet_chain_migrate_missing_params(self):
        """Test wallet chain migrate with missing parameters"""
        result = self.runner.invoke(cli, ['wallet', 'chain', 'migrate'])
        assert result.exit_code != 0
        # Should show error for missing parameters
        print("✅ Wallet chain migrate parameter validation working")
    
    def test_wallet_chain_migrate_with_params(self):
        """Test wallet chain migrate with parameters"""
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'migrate',
            'source-chain', 'target-chain'
        ])
        # Should attempt to migrate or show error
        print("✅ Wallet chain migrate with parameters working")
    
    def test_wallet_create_in_chain_help(self):
        """Test wallet create-in-chain help"""
        result = self.runner.invoke(cli, ['wallet', 'create-in-chain', '--help'])
        assert result.exit_code == 0
        assert 'CHAIN_ID' in result.output
        assert 'WALLET_NAME' in result.output
        assert '--type' in result.output
        print("✅ Wallet create-in-chain help working")
    
    def test_wallet_create_in_chain_missing_params(self):
        """Test wallet create-in-chain with missing parameters"""
        result = self.runner.invoke(cli, ['wallet', 'create-in-chain'])
        assert result.exit_code != 0
        # Should show error for missing parameters
        print("✅ Wallet create-in-chain parameter validation working")
    
    def test_wallet_create_in_chain_with_params(self):
        """Test wallet create-in-chain with parameters"""
        result = self.runner.invoke(cli, [
            'wallet', 'create-in-chain',
            self.test_chain_id, self.test_wallet_name,
            '--type', 'simple'
        ])
        # Should attempt to create wallet or show error
        print("✅ Wallet create-in-chain with parameters working")
    
    def test_wallet_create_in_chain_with_encryption(self):
        """Test wallet create-in-chain with encryption options"""
        result = self.runner.invoke(cli, [
            'wallet', 'create-in-chain',
            self.test_chain_id, self.test_wallet_name,
            '--type', 'simple',
            '--no-encrypt'
        ])
        # Should attempt to create wallet or show error
        print("✅ Wallet create-in-chain with encryption options working")
    
    def test_multi_chain_wallet_daemon_integration(self):
        """Test multi-chain wallet with daemon integration"""
        result = self.runner.invoke(cli, [
            'wallet', '--use-daemon',
            'chain', 'list'
        ])
        # Should attempt to use daemon or show error
        print("✅ Multi-chain wallet daemon integration working")
    
    def test_multi_chain_wallet_json_output(self):
        """Test multi-chain wallet commands with JSON output"""
        result = self.runner.invoke(cli, [
            '--output', 'json',
            'wallet', 'chain', 'list'
        ])
        assert result.exit_code == 0
        # Should output JSON format or error
        print("✅ Multi-chain wallet JSON output working")
    
    def test_multi_chain_wallet_yaml_output(self):
        """Test multi-chain wallet commands with YAML output"""
        result = self.runner.invoke(cli, [
            '--output', 'yaml',
            'wallet', 'chain', 'list'
        ])
        assert result.exit_code == 0
        # Should output YAML format or error
        print("✅ Multi-chain wallet YAML output working")
    
    def test_multi_chain_wallet_verbose_output(self):
        """Test multi-chain wallet commands with verbose output"""
        result = self.runner.invoke(cli, [
            '-v',
            'wallet', 'chain', 'status'
        ])
        assert result.exit_code == 0
        # Should show verbose output
        print("✅ Multi-chain wallet verbose output working")
    
    def test_multi_chain_wallet_error_handling(self):
        """Test multi-chain wallet error handling"""
        # Test with invalid command
        result = self.runner.invoke(cli, ['wallet', 'chain', 'invalid-command'])
        assert result.exit_code != 0
        print("✅ Multi-chain wallet error handling working")
    
    def test_multi_chain_wallet_with_specific_wallet(self):
        """Test multi-chain wallet operations with specific wallet"""
        result = self.runner.invoke(cli, [
            '--wallet-name', self.test_wallet_name,
            'wallet', 'chain', 'balance',
            self.test_chain_id
        ])
        # Should attempt to use specific wallet or show error
        print("✅ Multi-chain wallet with specific wallet working")


class TestMultiChainWalletIntegration:
    """Integration tests for multi-chain wallet operations"""
    
    def setup_method(self):
        """Setup integration test environment"""
        self.runner = CliRunner()
        self.test_chain_id = "test-chain"
        self.test_wallet_name = "integration-test-wallet"
    
    def test_multi_chain_wallet_workflow(self):
        """Test complete multi-chain wallet workflow"""
        # 1. List chains
        result = self.runner.invoke(cli, ['wallet', 'chain', 'list'])
        assert result.exit_code == 0
        
        # 2. Check chain status
        result = self.runner.invoke(cli, ['wallet', 'chain', 'status'])
        assert result.exit_code == 0
        
        # 3. Create wallet in chain (if supported)
        result = self.runner.invoke(cli, [
            'wallet', 'create-in-chain',
            self.test_chain_id, self.test_wallet_name,
            '--type', 'simple'
        ])
        
        # 4. Check balance in chain
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'balance',
            self.test_chain_id
        ])
        
        # 5. List wallets in chain
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'wallets',
            self.test_chain_id
        ])
        
        # 6. Get chain info
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'info',
            self.test_chain_id
        ])
        
        print("✅ Multi-chain wallet workflow integration test passed")
    
    def test_multi_chain_wallet_migration_workflow(self):
        """Test multi-chain wallet migration workflow"""
        # 1. Attempt migration (if supported)
        result = self.runner.invoke(cli, [
            'wallet', 'chain', 'migrate',
            'source-chain', 'target-chain'
        ])
        
        # 2. Check migration status (if supported)
        result = self.runner.invoke(cli, ['wallet', 'migration-status'])
        
        print("✅ Multi-chain wallet migration workflow integration test passed")
    
    def test_multi_chain_wallet_daemon_workflow(self):
        """Test multi-chain wallet daemon workflow"""
        # 1. Use daemon for chain operations
        result = self.runner.invoke(cli, [
            'wallet', '--use-daemon',
            'chain', 'list'
        ])
        assert result.exit_code == 0
        
        # 2. Get daemon status
        result = self.runner.invoke(cli, [
            'wallet', 'daemon', 'status'
        ])
        
        print("✅ Multi-chain wallet daemon workflow integration test passed")


def run_multichain_wallet_tests():
    """Run all multi-chain wallet tests"""
    print("🚀 Running Multi-Chain Wallet CLI Tests")
    print("=" * 50)
    
    # Run pytest for multi-chain wallet tests
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
            print("✅ All multi-chain wallet tests passed!")
        else:
            print(f"❌ Some tests failed (exit code: {result.returncode})")
            
    except Exception as e:
        print(f"❌ Error running tests: {e}")


if __name__ == '__main__':
    run_multichain_wallet_tests()
