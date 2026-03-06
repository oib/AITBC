"""
Test Wallet to Chain Connection

Tests for connecting wallets to blockchain chains through the CLI
using the multi-chain wallet daemon integration.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import json

from aitbc_cli.wallet_daemon_client import WalletDaemonClient, ChainInfo, WalletInfo
from aitbc_cli.dual_mode_wallet_adapter import DualModeWalletAdapter
from aitbc_cli.config import Config


class TestWalletChainConnection:
    """Test wallet to chain connection functionality"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.config.wallet_url = "http://localhost:8002"
        
        # Create adapter in daemon mode
        self.adapter = DualModeWalletAdapter(self.config, use_daemon=True)
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_list_chains_daemon_mode(self):
        """Test listing chains in daemon mode"""
        # Mock chain data
        mock_chains = [
            ChainInfo(
                chain_id="ait-devnet",
                name="AITBC Development Network",
                status="active",
                coordinator_url="http://localhost:8011",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                wallet_count=5,
                recent_activity=10
            ),
            ChainInfo(
                chain_id="ait-testnet",
                name="AITBC Test Network",
                status="active",
                coordinator_url="http://localhost:8012",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                wallet_count=3,
                recent_activity=5
            )
        ]
        
        with patch.object(self.adapter.daemon_client, 'list_chains', return_value=mock_chains):
            with patch.object(self.adapter, 'is_daemon_available', return_value=True):
                chains = self.adapter.list_chains()
                
                assert len(chains) == 2
                assert chains[0]["chain_id"] == "ait-devnet"
                assert chains[1]["chain_id"] == "ait-testnet"
                assert chains[0]["wallet_count"] == 5
                assert chains[1]["wallet_count"] == 3
    
    def test_create_chain_daemon_mode(self):
        """Test creating a chain in daemon mode"""
        mock_chain = ChainInfo(
            chain_id="ait-mainnet",
            name="AITBC Main Network",
            status="active",
            coordinator_url="http://localhost:8013",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            wallet_count=0,
            recent_activity=0
        )
        
        with patch.object(self.adapter.daemon_client, 'create_chain', return_value=mock_chain):
            with patch.object(self.adapter, 'is_daemon_available', return_value=True):
                chain = self.adapter.create_chain(
                    "ait-mainnet",
                    "AITBC Main Network",
                    "http://localhost:8013",
                    "mainnet-api-key"
                )
                
                assert chain is not None
                assert chain["chain_id"] == "ait-mainnet"
                assert chain["name"] == "AITBC Main Network"
                assert chain["status"] == "active"
    
    def test_create_wallet_in_chain(self):
        """Test creating a wallet in a specific chain"""
        mock_wallet = WalletInfo(
            wallet_id="test-wallet",
            chain_id="ait-devnet",
            public_key="test-public-key",
            address="test-address",
            created_at="2026-01-01T00:00:00Z",
            metadata={}
        )
        
        with patch.object(self.adapter.daemon_client, 'create_wallet_in_chain', return_value=mock_wallet):
            with patch.object(self.adapter, 'is_daemon_available', return_value=True):
                result = self.adapter.create_wallet_in_chain(
                    "ait-devnet",
                    "test-wallet",
                    "password123"
                )
                
                assert result is not None
                assert result["chain_id"] == "ait-devnet"
                assert result["wallet_name"] == "test-wallet"
                assert result["public_key"] == "test-public-key"
                assert result["mode"] == "daemon"
    
    def test_list_wallets_in_chain(self):
        """Test listing wallets in a specific chain"""
        mock_wallets = [
            WalletInfo(
                wallet_id="wallet1",
                chain_id="ait-devnet",
                public_key="pub1",
                address="addr1",
                created_at="2026-01-01T00:00:00Z",
                metadata={}
            ),
            WalletInfo(
                wallet_id="wallet2",
                chain_id="ait-devnet",
                public_key="pub2",
                address="addr2",
                created_at="2026-01-01T00:00:00Z",
                metadata={}
            )
        ]
        
        with patch.object(self.adapter.daemon_client, 'list_wallets_in_chain', return_value=mock_wallets):
            with patch.object(self.adapter, 'is_daemon_available', return_value=True):
                wallets = self.adapter.list_wallets_in_chain("ait-devnet")
                
                assert len(wallets) == 2
                assert wallets[0]["chain_id"] == "ait-devnet"
                assert wallets[0]["wallet_name"] == "wallet1"
                assert wallets[1]["wallet_name"] == "wallet2"
    
    def test_get_wallet_balance_in_chain(self):
        """Test getting wallet balance in a specific chain"""
        mock_balance = Mock()
        mock_balance.balance = 100.5
        
        with patch.object(self.adapter.daemon_client, 'get_wallet_balance_in_chain', return_value=mock_balance):
            with patch.object(self.adapter, 'is_daemon_available', return_value=True):
                balance = self.adapter.get_wallet_balance_in_chain("ait-devnet", "test-wallet")
                
                assert balance == 100.5
    
    def test_migrate_wallet_between_chains(self):
        """Test migrating wallet between chains"""
        mock_result = Mock()
        mock_result.success = True
        mock_result.source_wallet = WalletInfo(
            wallet_id="test-wallet",
            chain_id="ait-devnet",
            public_key="pub-key",
            address="addr"
        )
        mock_result.target_wallet = WalletInfo(
            wallet_id="test-wallet",
            chain_id="ait-testnet",
            public_key="pub-key",
            address="addr"
        )
        mock_result.migration_timestamp = "2026-01-01T00:00:00Z"
        
        with patch.object(self.adapter.daemon_client, 'migrate_wallet', return_value=mock_result):
            with patch.object(self.adapter, 'is_daemon_available', return_value=True):
                result = self.adapter.migrate_wallet(
                    "ait-devnet",
                    "ait-testnet",
                    "test-wallet",
                    "password123"
                )
                
                assert result is not None
                assert result["success"] is True
                assert result["source_wallet"]["chain_id"] == "ait-devnet"
                assert result["target_wallet"]["chain_id"] == "ait-testnet"
    
    def test_get_chain_status(self):
        """Test getting overall chain status"""
        mock_status = {
            "total_chains": 3,
            "active_chains": 2,
            "total_wallets": 25,
            "chains": [
                {
                    "chain_id": "ait-devnet",
                    "name": "AITBC Development Network",
                    "status": "active",
                    "wallet_count": 15,
                    "recent_activity": 10
                },
                {
                    "chain_id": "ait-testnet",
                    "name": "AITBC Test Network",
                    "status": "active",
                    "wallet_count": 8,
                    "recent_activity": 5
                },
                {
                    "chain_id": "ait-mainnet",
                    "name": "AITBC Main Network",
                    "status": "inactive",
                    "wallet_count": 2,
                    "recent_activity": 0
                }
            ]
        }
        
        with patch.object(self.adapter.daemon_client, 'get_chain_status', return_value=mock_status):
            with patch.object(self.adapter, 'is_daemon_available', return_value=True):
                status = self.adapter.get_chain_status()
                
                assert status["total_chains"] == 3
                assert status["active_chains"] == 2
                assert status["total_wallets"] == 25
                assert len(status["chains"]) == 3
    
    def test_chain_operations_require_daemon_mode(self):
        """Test that chain operations require daemon mode"""
        # Create adapter in file mode
        file_adapter = DualModeWalletAdapter(self.config, use_daemon=False)
        
        # All chain operations should fail in file mode
        assert file_adapter.list_chains() == []
        assert file_adapter.create_chain("test", "Test", "http://localhost:8011", "key") is None
        assert file_adapter.create_wallet_in_chain("test", "wallet", "pass") is None
        assert file_adapter.list_wallets_in_chain("test") == []
        assert file_adapter.get_wallet_info_in_chain("test", "wallet") is None
        assert file_adapter.get_wallet_balance_in_chain("test", "wallet") is None
        assert file_adapter.migrate_wallet("src", "dst", "wallet", "pass") is None
        assert file_adapter.get_chain_status()["status"] == "disabled"
    
    def test_chain_operations_require_daemon_availability(self):
        """Test that chain operations require daemon availability"""
        # Mock daemon as unavailable
        with patch.object(self.adapter, 'is_daemon_available', return_value=False):
            # All chain operations should fail when daemon is unavailable
            assert self.adapter.list_chains() == []
            assert self.adapter.create_chain("test", "Test", "http://localhost:8011", "key") is None
            assert self.adapter.create_wallet_in_chain("test", "wallet", "pass") is None
            assert self.adapter.list_wallets_in_chain("test") == []
            assert self.adapter.get_wallet_info_in_chain("test", "wallet") is None
            assert self.adapter.get_wallet_balance_in_chain("test", "wallet") is None
            assert self.adapter.migrate_wallet("src", "dst", "wallet", "pass") is None
            assert self.adapter.get_chain_status()["status"] == "disabled"


class TestWalletChainCLICommands:
    """Test CLI commands for wallet-chain operations"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.config.wallet_url = "http://localhost:8002"
        
        # Create CLI context
        self.ctx = {
            "wallet_adapter": DualModeWalletAdapter(self.config, use_daemon=True),
            "use_daemon": True,
            "output_format": "json"
        }
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('aitbc_cli.commands.wallet.output')
    def test_cli_chain_list_command(self, mock_output):
        """Test CLI chain list command"""
        mock_chains = [
            ChainInfo(
                chain_id="ait-devnet",
                name="AITBC Development Network",
                status="active",
                coordinator_url="http://localhost:8011",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                wallet_count=5,
                recent_activity=10
            )
        ]
        
        with patch.object(self.ctx["wallet_adapter"], 'is_daemon_available', return_value=True):
            with patch.object(self.ctx["wallet_adapter"], 'list_chains', return_value=mock_chains):
                from aitbc_cli.commands.wallet import chain
                
                # Mock the CLI command
                chain_list = chain.get_command(None, "list")
                chain_list.callback(self.ctx)
                
                # Verify output was called
                mock_output.assert_called_once()
                call_args = mock_output.call_args[0][0]
                assert call_args["count"] == 1
                assert call_args["mode"] == "daemon"
    
    @patch('aitbc_cli.commands.wallet.success')
    @patch('aitbc_cli.commands.wallet.output')
    def test_cli_chain_create_command(self, mock_output, mock_success):
        """Test CLI chain create command"""
        mock_chain = ChainInfo(
            chain_id="ait-mainnet",
            name="AITBC Main Network",
            status="active",
            coordinator_url="http://localhost:8013",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            wallet_count=0,
            recent_activity=0
        )
        
        with patch.object(self.ctx["wallet_adapter"], 'is_daemon_available', return_value=True):
            with patch.object(self.ctx["wallet_adapter"], 'create_chain', return_value=mock_chain):
                from aitbc_cli.commands.wallet import chain
                
                # Mock the CLI command
                chain_create = chain.get_command(None, "create")
                chain_create.callback(self.ctx, "ait-mainnet", "AITBC Main Network", "http://localhost:8013", "mainnet-key")
                
                # Verify success and output were called
                mock_success.assert_called_once_with("Created chain: ait-mainnet")
                mock_output.assert_called_once()
    
    @patch('aitbc_cli.commands.wallet.success')
    @patch('aitbc_cli.commands.wallet.output')
    @patch('aitbc_cli.commands.wallet.getpass')
    def test_cli_create_wallet_in_chain_command(self, mock_getpass, mock_output, mock_success):
        """Test CLI create wallet in chain command"""
        mock_wallet = WalletInfo(
            wallet_id="test-wallet",
            chain_id="ait-devnet",
            public_key="test-public-key",
            address="test-address",
            created_at="2026-01-01T00:00:00Z",
            metadata={}
        )
        
        mock_getpass.getpass.return_value = "password123"
        
        with patch.object(self.ctx["wallet_adapter"], 'is_daemon_available', return_value=True):
            with patch.object(self.ctx["wallet_adapter"], 'create_wallet_in_chain', return_value=mock_wallet):
                from aitbc_cli.commands.wallet import wallet
                
                # Mock the CLI command
                create_in_chain = wallet.get_command(None, "create-in-chain")
                create_in_chain.callback(self.ctx, "ait-devnet", "test-wallet")
                
                # Verify success and output were called
                mock_success.assert_called_once_with("Created wallet 'test-wallet' in chain 'ait-devnet'")
                mock_output.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
