"""
Wallet Daemon Client Tests
Tests for wallet daemon client
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestChainInfo:
    """Test ChainInfo dataclass"""

    def test_chain_info_creation(self):
        """Test creating ChainInfo"""
        from aitbc_cli.utils.wallet_daemon_client import ChainInfo

        info = ChainInfo(
            chain_id="ait-mainnet",
            name="Mainnet",
            status="active",
            coordinator_url="http://localhost:8000",
            created_at="2024-01-01",
            updated_at="2024-01-02",
            wallet_count=10,
            recent_activity=5,
        )

        assert info.chain_id == "ait-mainnet"
        assert info.wallet_count == 10


class TestWalletInfo:
    """Test WalletInfo dataclass"""

    def test_wallet_info_creation(self):
        """Test creating WalletInfo"""
        from aitbc_cli.utils.wallet_daemon_client import WalletInfo

        info = WalletInfo(
            wallet_id="wallet123",
            chain_id="ait-mainnet",
            public_key="pubkey123",
            address="aitbc1abc",
            created_at="2024-01-01",
            metadata={"label": "test"},
        )

        assert info.wallet_id == "wallet123"
        assert info.address == "aitbc1abc"


class TestWalletBalance:
    """Test WalletBalance dataclass"""

    def test_wallet_balance_creation(self):
        """Test creating WalletBalance"""
        from aitbc_cli.utils.wallet_daemon_client import WalletBalance

        balance = WalletBalance(
            wallet_id="wallet123", chain_id="ait-mainnet", balance=100.5, address="aitbc1abc", last_updated="2024-01-01"
        )

        assert balance.balance == 100.5
        assert balance.wallet_id == "wallet123"


class TestWalletMigrationResult:
    """Test WalletMigrationResult dataclass"""

    def test_wallet_migration_result_creation(self):
        """Test creating WalletMigrationResult"""
        from aitbc_cli.utils.wallet_daemon_client import WalletInfo, WalletMigrationResult

        source = WalletInfo(wallet_id="wallet1", chain_id="chain1", public_key="pub1")
        target = WalletInfo(wallet_id="wallet2", chain_id="chain2", public_key="pub2")

        result = WalletMigrationResult(
            success=True, source_wallet=source, target_wallet=target, migration_timestamp="2024-01-01"
        )

        assert result.success is True
        assert result.source_wallet.wallet_id == "wallet1"


class TestWalletDaemonClient:
    """Test WalletDaemonClient class"""

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_init(self, mock_client):
        """Test WalletDaemonClient initialization"""
        from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        config.timeout = 30

        client = WalletDaemonClient(config)

        assert client.config == config
        assert client.base_url == "http://localhost:8000"
        assert client.timeout == 30

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_init_default_timeout(self, mock_client):
        """Test initialization with default timeout"""
        from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        delattr(config, "timeout")

        client = WalletDaemonClient(config)

        assert client.timeout == 30

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_is_available_success(self, mock_client):
        """Test daemon availability check when available"""
        from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        config.timeout = 30

        mock_http = Mock()
        mock_http.get.return_value = {"status": "ok"}
        mock_client.return_value = mock_http

        client = WalletDaemonClient(config)

        assert client.is_available() is True

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_is_available_network_error(self, mock_client):
        """Test daemon availability check with network error"""
        from aitbc_cli.utils.wallet_daemon_client import NetworkError, WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        config.timeout = 30

        mock_http = Mock()
        mock_http.get.side_effect = NetworkError("Connection failed")
        mock_client.return_value = mock_http

        client = WalletDaemonClient(config)

        assert client.is_available() is False

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_is_available_generic_error(self, mock_client):
        """Test daemon availability check with generic error"""
        from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        config.timeout = 30

        mock_http = Mock()
        mock_http.get.side_effect = Exception("Unexpected error")
        mock_client.return_value = mock_http

        client = WalletDaemonClient(config)

        assert client.is_available() is False

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_get_status_success(self, mock_client):
        """Test getting daemon status successfully"""
        from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        config.timeout = 30

        mock_http = Mock()
        mock_http.get.return_value = {"status": "running", "version": "1.0"}
        mock_client.return_value = mock_http

        client = WalletDaemonClient(config)

        status = client.get_status()

        assert status["status"] == "running"
        assert status["version"] == "1.0"

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_get_status_network_error(self, mock_client):
        """Test getting daemon status with network error"""
        from aitbc_cli.utils.wallet_daemon_client import NetworkError, WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        config.timeout = 30

        mock_http = Mock()
        mock_http.get.side_effect = NetworkError("Connection failed")
        mock_client.return_value = mock_http

        client = WalletDaemonClient(config)

        status = client.get_status()

        assert status["status"] == "unavailable"
        assert "error" in status

    @patch("aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient")
    def test_get_status_generic_error(self, mock_client):
        """Test getting daemon status with generic error"""
        from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient

        config = Mock()
        config.wallet_url = "http://localhost:8000"
        config.timeout = 30

        mock_http = Mock()
        mock_http.get.side_effect = Exception("Unexpected error")
        mock_client.return_value = mock_http

        client = WalletDaemonClient(config)

        status = client.get_status()

        assert status["status"] == "error"
        assert "error" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
