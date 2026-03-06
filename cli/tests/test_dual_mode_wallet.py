"""Dual-Mode Wallet Tests

Tests for the dual-mode wallet adapter that supports both file-based
and daemon-based wallet operations.
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from click.testing import CliRunner

from aitbc_cli.config import Config
from aitbc_cli.dual_mode_wallet_adapter import DualModeWalletAdapter
from aitbc_cli.wallet_daemon_client import WalletDaemonClient, WalletInfo, WalletBalance
from aitbc_cli.commands.wallet import wallet
from aitbc_cli.wallet_migration_service import WalletMigrationService


class TestWalletDaemonClient:
    """Test the wallet daemon client"""
    
    def setup_method(self):
        """Set up test configuration"""
        self.config = Config()
        self.config.wallet_url = "http://localhost:8002"
        self.client = WalletDaemonClient(self.config)
    
    def test_client_initialization(self):
        """Test client initialization"""
        assert self.client.base_url == "http://localhost:8002"
        assert self.client.timeout == 30
    
    @patch('aitbc_cli.wallet_daemon_client.httpx.Client')
    def test_is_available_success(self, mock_client):
        """Test daemon availability check - success"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        assert self.client.is_available() is True
    
    @patch('aitbc_cli.wallet_daemon_client.httpx.Client')
    def test_is_available_failure(self, mock_client):
        """Test daemon availability check - failure"""
        mock_client.return_value.__enter__.side_effect = Exception("Connection failed")
        
        assert self.client.is_available() is False
    
    @patch('aitbc_cli.wallet_daemon_client.httpx.Client')
    def test_create_wallet_success(self, mock_client):
        """Test wallet creation - success"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "wallet_id": "test-wallet",
            "public_key": "0x123456",
            "address": "aitbc1test",
            "created_at": "2023-01-01T00:00:00Z",
            "metadata": {}
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        result = self.client.create_wallet("test-wallet", "password123")
        
        assert isinstance(result, WalletInfo)
        assert result.wallet_id == "test-wallet"
        assert result.public_key == "0x123456"
        assert result.address == "aitbc1test"
    
    @patch('aitbc_cli.wallet_daemon_client.httpx.Client')
    def test_list_wallets_success(self, mock_client):
        """Test wallet listing - success"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "wallets": [
                {
                    "wallet_id": "wallet1",
                    "public_key": "0x111",
                    "address": "aitbc1wallet1",
                    "created_at": "2023-01-01T00:00:00Z"
                },
                {
                    "wallet_id": "wallet2", 
                    "public_key": "0x222",
                    "address": "aitbc1wallet2",
                    "created_at": "2023-01-02T00:00:00Z"
                }
            ]
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.client.list_wallets()
        
        assert len(result) == 2
        assert result[0].wallet_id == "wallet1"
        assert result[1].wallet_id == "wallet2"
    
    @patch('aitbc_cli.wallet_daemon_client.httpx.Client')
    def test_get_wallet_balance_success(self, mock_client):
        """Test wallet balance retrieval - success"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "wallet_id": "test-wallet",
            "balance": 100.5,
            "address": "aitbc1test",
            "last_updated": "2023-01-01T00:00:00Z"
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        result = self.client.get_wallet_balance("test-wallet")
        
        assert isinstance(result, WalletBalance)
        assert result.wallet_id == "test-wallet"
        assert result.balance == 100.5


class TestDualModeWalletAdapter:
    """Test the dual-mode wallet adapter"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.config.config_dir = self.temp_dir
        
        # Mock wallet directory
        self.wallet_dir = self.temp_dir / "wallets"
        self.wallet_dir.mkdir(parents=True, exist_ok=True)
    
    def teardown_method(self):
        """Clean up test environment"""
        shutil.rmtree(self.temp_dir)
    
    def test_file_mode_initialization(self):
        """Test adapter initialization in file mode"""
        adapter = DualModeWalletAdapter(self.config, use_daemon=False)
        
        assert adapter.use_daemon is False
        assert adapter.daemon_client is None
        assert adapter.wallet_dir == Path.home() / ".aitbc" / "wallets"
    
    def test_daemon_mode_initialization(self):
        """Test adapter initialization in daemon mode"""
        adapter = DualModeWalletAdapter(self.config, use_daemon=True)
        
        assert adapter.use_daemon is True
        assert adapter.daemon_client is not None
        assert isinstance(adapter.daemon_client, WalletDaemonClient)
    
    def test_create_wallet_file_mode(self):
        """Test wallet creation in file mode"""
        adapter = DualModeWalletAdapter(self.config, use_daemon=False)
        
        with patch('aitbc_cli.dual_mode_wallet_adapter.Path.home') as mock_home:
            mock_home.return_value = self.temp_dir
            adapter.wallet_dir = self.temp_dir / "wallets"
            
            result = adapter.create_wallet("test-wallet", "password123", "hd")
            
            assert result["mode"] == "file"
            assert result["wallet_name"] == "test-wallet"
            assert result["wallet_type"] == "hd"
            
            # Check wallet file was created
            wallet_file = self.wallet_dir / "test-wallet.json"
            assert wallet_file.exists()
    
    @patch('aitbc_cli.dual_mode_wallet_adapter.Path.home')
    def test_create_wallet_daemon_mode_success(self, mock_home):
        """Test wallet creation in daemon mode - success"""
        mock_home.return_value = self.temp_dir
        
        adapter = DualModeWalletAdapter(self.config, use_daemon=True)
        
        # Mock daemon client
        mock_client = Mock()
        mock_client.is_available.return_value = True
        mock_client.create_wallet.return_value = WalletInfo(
            wallet_id="test-wallet",
            public_key="0x123456",
            address="aitbc1test",
            created_at="2023-01-01T00:00:00Z"
        )
        adapter.daemon_client = mock_client
        
        result = adapter.create_wallet("test-wallet", "password123", metadata={})
        
        assert result["mode"] == "daemon"
        assert result["wallet_name"] == "test-wallet"
        assert result["wallet_id"] == "test-wallet"
        mock_client.create_wallet.assert_called_once()
    
    @patch('aitbc_cli.dual_mode_wallet_adapter.Path.home')
    def test_create_wallet_daemon_mode_fallback(self, mock_home):
        """Test wallet creation in daemon mode - fallback to file"""
        mock_home.return_value = self.temp_dir
        
        adapter = DualModeWalletAdapter(self.config, use_daemon=True)
        
        # Mock unavailable daemon
        mock_client = Mock()
        mock_client.is_available.return_value = False
        adapter.daemon_client = mock_client
        
        result = adapter.create_wallet("test-wallet", "password123", "hd")
        
        assert result["mode"] == "file"
        assert result["wallet_name"] == "test-wallet"
    
    @patch('aitbc_cli.dual_mode_wallet_adapter.Path.home')
    def test_list_wallets_file_mode(self, mock_home):
        """Test wallet listing in file mode"""
        mock_home.return_value = self.temp_dir
        
        # Create test wallets
        wallet1_data = {
            "name": "wallet1",
            "address": "aitbc1wallet1",
            "balance": 10.0,
            "wallet_type": "hd",
            "created_at": "2023-01-01T00:00:00Z"
        }
        
        wallet2_data = {
            "name": "wallet2", 
            "address": "aitbc1wallet2",
            "balance": 20.0,
            "wallet_type": "simple",
            "created_at": "2023-01-02T00:00:00Z"
        }
        
        with open(self.wallet_dir / "wallet1.json", "w") as f:
            json.dump(wallet1_data, f)
        with open(self.wallet_dir / "wallet2.json", "w") as f:
            json.dump(wallet2_data, f)
        
        adapter = DualModeWalletAdapter(self.config, use_daemon=False)
        adapter.wallet_dir = self.wallet_dir
        
        result = adapter.list_wallets()
        
        assert len(result) == 2
        assert result[0]["wallet_name"] == "wallet1"
        assert result[0]["mode"] == "file"
        assert result[1]["wallet_name"] == "wallet2"
        assert result[1]["mode"] == "file"


class TestWalletCommands:
    """Test wallet commands with dual-mode support"""
    
    def setup_method(self):
        """Set up test environment"""
        self.runner = CliRunner()
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up test environment"""
        shutil.rmtree(self.temp_dir)
    
    @patch('aitbc_cli.commands.wallet.Path.home')
    def test_wallet_create_file_mode(self, mock_home):
        """Test wallet creation command in file mode"""
        mock_home.return_value = self.temp_dir
        
        result = self.runner.invoke(wallet, [
            'create', 'test-wallet', '--type', 'simple', '--no-encrypt'
        ])
        
        assert result.exit_code == 0
        assert 'Created file wallet' in result.output
    
    @patch('aitbc_cli.commands.wallet.Path.home')
    def test_wallet_create_daemon_mode_unavailable(self, mock_home):
        """Test wallet creation command in daemon mode when daemon unavailable"""
        mock_home.return_value = self.temp_dir
        
        result = self.runner.invoke(wallet, [
            '--use-daemon', 'create', 'test-wallet', '--type', 'simple', '--no-encrypt'
        ])
        
        assert result.exit_code == 0
        assert 'Falling back to file-based wallet' in result.output
    
    @patch('aitbc_cli.commands.wallet.Path.home')
    def test_wallet_list_file_mode(self, mock_home):
        """Test wallet listing command in file mode"""
        mock_home.return_value = self.temp_dir
        
        # Create a test wallet first
        wallet_dir = self.temp_dir / ".aitbc" / "wallets"
        wallet_dir.mkdir(parents=True, exist_ok=True)
        
        wallet_data = {
            "name": "test-wallet",
            "address": "aitbc1test",
            "balance": 10.0,
            "wallet_type": "hd",
            "created_at": "2023-01-01T00:00:00Z"
        }
        
        with open(wallet_dir / "test-wallet.json", "w") as f:
            json.dump(wallet_data, f)
        
        result = self.runner.invoke(wallet, ['list'])
        
        assert result.exit_code == 0
        assert 'test-wallet' in result.output
    
    @patch('aitbc_cli.commands.wallet.Path.home')
    def test_wallet_balance_file_mode(self, mock_home):
        """Test wallet balance command in file mode"""
        mock_home.return_value = self.temp_dir
        
        # Create a test wallet first
        wallet_dir = self.temp_dir / ".aitbc" / "wallets"
        wallet_dir.mkdir(parents=True, exist_ok=True)
        
        wallet_data = {
            "name": "test-wallet",
            "address": "aitbc1test",
            "balance": 25.5,
            "wallet_type": "hd",
            "created_at": "2023-01-01T00:00:00Z"
        }
        
        with open(wallet_dir / "test-wallet.json", "w") as f:
            json.dump(wallet_data, f)
        
        result = self.runner.invoke(wallet, ['balance'])
        
        assert result.exit_code == 0
        assert '25.5' in result.output


class TestWalletMigrationService:
    """Test wallet migration service"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.config.config_dir = self.temp_dir
        
        # Mock wallet directory
        self.wallet_dir = self.temp_dir / "wallets"
        self.wallet_dir.mkdir(parents=True, exist_ok=True)
    
    def teardown_method(self):
        """Clean up test environment"""
        shutil.rmtree(self.temp_dir)
    
    @patch('aitbc_cli.wallet_migration_service.Path.home')
    def test_migration_status_daemon_unavailable(self, mock_home):
        """Test migration status when daemon is unavailable"""
        mock_home.return_value = self.temp_dir
        
        migration_service = WalletMigrationService(self.config)
        
        # Create test file wallet
        wallet_data = {
            "name": "test-wallet",
            "address": "aitbc1test",
            "balance": 10.0,
            "wallet_type": "hd",
            "created_at": "2023-01-01T00:00:00Z"
        }
        
        with open(self.wallet_dir / "test-wallet.json", "w") as f:
            json.dump(wallet_data, f)
        
        status = migration_service.get_migration_status()
        
        assert status["daemon_available"] is False
        assert status["total_file_wallets"] == 1
        assert status["total_daemon_wallets"] == 0
        assert "test-wallet" in status["file_only_wallets"]
    
    @patch('aitbc_cli.wallet_migration_service.Path.home')
    def test_migrate_to_daemon_success(self, mock_home):
        """Test migration to daemon - success"""
        mock_home.return_value = self.temp_dir
        
        migration_service = WalletMigrationService(self.config)
        
        # Create test file wallet
        wallet_data = {
            "name": "test-wallet",
            "address": "aitbc1test",
            "balance": 10.0,
            "wallet_type": "hd",
            "created_at": "2023-01-01T00:00:00Z",
            "transactions": []
        }
        
        with open(self.wallet_dir / "test-wallet.json", "w") as f:
            json.dump(wallet_data, f)
        
        # Mock successful daemon migration
        mock_adapter = Mock()
        mock_adapter.is_daemon_available.return_value = True
        mock_adapter.get_wallet_info.return_value = None  # Wallet doesn't exist in daemon
        mock_adapter.create_wallet.return_value = {
            "wallet_id": "test-wallet",
            "public_key": "0x123456",
            "address": "aitbc1test"
        }
        migration_service.daemon_adapter = mock_adapter
        
        result = migration_service.migrate_to_daemon("test-wallet", "password123")
        
        assert result["wallet_name"] == "test-wallet"
        assert result["source_mode"] == "file"
        assert result["target_mode"] == "daemon"
        assert result["original_balance"] == 10.0


if __name__ == "__main__":
    pytest.main([__file__])
