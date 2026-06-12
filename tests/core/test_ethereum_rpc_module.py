"""
Tests for AITBC Ethereum RPC module (ethereum_rpc.py)
This module has 0% coverage and 124 statements.
"""

from unittest.mock import Mock, patch

import pytest

# Import the module normally
from aitbc import ethereum_rpc

# ============================================================================
# EthereumConfig Tests
# ============================================================================

class TestEthereumConfig:
    """Test EthereumConfig dataclass"""

    def test_initialization_defaults(self):
        config = ethereum_rpc.EthereumConfig()
        assert config.network == "sepolia"  # Default from env or fallback
        assert config.rpc_url is None
        assert config.infura_key is None
        assert config.alchemy_key is None
        assert config.timeout == 10
        assert config.max_retries == 3

    def test_initialization_custom(self):
        config = ethereum_rpc.EthereumConfig(
            network="mainnet",
            rpc_url="https://custom.rpc",
            infura_key="test_infura",
            alchemy_key="test_alchemy",
            timeout=30,
            max_retries=5
        )
        assert config.network == "mainnet"
        assert config.rpc_url == "https://custom.rpc"
        assert config.infura_key == "test_infura"
        assert config.alchemy_key == "test_alchemy"
        assert config.timeout == 30
        assert config.max_retries == 5

    def test_get_rpc_urls_with_custom_url(self):
        config = ethereum_rpc.EthereumConfig(rpc_url="https://custom.rpc")
        urls = config.get_rpc_urls()
        assert urls[0] == "https://custom.rpc"

    def test_get_rpc_urls_with_infura(self):
        config = ethereum_rpc.EthereumConfig(
            network="mainnet",
            infura_key="test_key"
        )
        urls = config.get_rpc_urls()
        assert "https://mainnet.infura.io/v3/test_key" in urls

    def test_get_rpc_urls_with_alchemy_mainnet(self):
        config = ethereum_rpc.EthereumConfig(
            network="mainnet",
            alchemy_key="test_key"
        )
        urls = config.get_rpc_urls()
        assert "https://eth-mainnet.g.alchemy.com/v2/test_key" in urls

    def test_get_rpc_urls_with_alchemy_sepolia(self):
        config = ethereum_rpc.EthereumConfig(
            network="sepolia",
            alchemy_key="test_key"
        )
        urls = config.get_rpc_urls()
        assert "https://eth-sepolia.g.alchemy.com/v2/test_key" in urls

    def test_get_rpc_urls_mainnet_public(self):
        config = ethereum_rpc.EthereumConfig(network="mainnet")
        urls = config.get_rpc_urls()
        assert "https://ethereum.publicnode.com" in urls
        assert "https://1rpc.io/eth" in urls

    def test_get_rpc_urls_sepolia_public(self):
        config = ethereum_rpc.EthereumConfig(network="sepolia")
        urls = config.get_rpc_urls()
        assert "https://ethereum-sepolia.publicnode.com" in urls
        assert "https://1rpc.io/sepolia" in urls

    def test_get_rpc_urls_priority_order(self):
        config = ethereum_rpc.EthereumConfig(
            rpc_url="https://custom.rpc",
            infura_key="infura_key",
            alchemy_key="alchemy_key"
        )
        urls = config.get_rpc_urls()
        assert urls[0] == "https://custom.rpc"
        assert "infura" in urls[1]
        assert "alchemy" in urls[2]


# ============================================================================
# EthereumRPCClient Tests
# ============================================================================

class TestEthereumRPCClient:
    """Test EthereumRPCClient class"""

    def test_initialization(self):
        config = ethereum_rpc.EthereumConfig(network="mainnet")
        client = ethereum_rpc.EthereumRPCClient(config)
        assert client.config == config
        assert client._w3 is None
        assert client._connected_url is None

    def test_initialization_default_config(self):
        client = ethereum_rpc.EthereumRPCClient()
        assert client.config is not None
        assert client._w3 is None

    def test_get_web3_web3_not_installed(self):
        client = ethereum_rpc.EthereumRPCClient()
        with patch.dict('sys.modules', {'web3': None}):
            with pytest.raises(RuntimeError, match="web3 package not installed"):
                client._get_web3()

    def test_get_web3_already_connected(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        client._w3 = mock_w3
        result = client._get_web3()
        assert result == mock_w3

    def test_is_connected_true(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_w3.is_connected.return_value = True
        client._w3 = mock_w3

        assert client.is_connected is True

    def test_is_connected_false(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_w3.is_connected.return_value = False
        client._w3 = mock_w3

        assert client.is_connected is False

    def test_is_connected_exception(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_w3.is_connected.side_effect = Exception("Test error")
        client._w3 = mock_w3

        assert client.is_connected is False

    def test_connected_url(self):
        client = ethereum_rpc.EthereumRPCClient()
        client._connected_url = "https://test.rpc"
        assert client.connected_url == "https://test.rpc"

    def test_connected_url_none(self):
        client = ethereum_rpc.EthereumRPCClient()
        assert client.connected_url is None

    def test_get_block_number(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_w3.eth.block_number = 12345
        client._w3 = mock_w3

        result = client.get_block_number()
        assert result == 12345

    def test_get_block(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_block = Mock()
        mock_block.number = 100
        mock_block.hash.hex.return_value = "0xhash123"
        mock_block.timestamp = 1234567890
        mock_block.transactions = [Mock(), Mock()]
        mock_block.gasUsed = 1000
        mock_block.gasLimit = 10000
        mock_w3.eth.get_block.return_value = mock_block
        client._w3 = mock_w3

        result = client.get_block(100)
        assert result["number"] == 100
        assert result["hash"] == "0xhash123"
        assert result["transaction_count"] == 2

    def test_get_transaction_not_found(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_w3.eth.get_transaction.side_effect = Exception("Not found")
        client._w3 = mock_w3

        result = client.get_transaction("0xtxhash")
        assert result is None

    def test_get_transaction_receipt(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_receipt = Mock()
        mock_receipt.blockNumber = 100
        mock_receipt.status = 1
        mock_receipt.gasUsed = 21000
        mock_receipt.contractAddress = "0xcontract"
        mock_receipt.logs = [Mock(), Mock()]
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt
        client._w3 = mock_w3

        result = client.get_transaction_receipt("0xtxhash")
        assert result["hash"] == "0xtxhash"
        assert result["block_number"] == 100
        assert result["status"] == 1
        assert result["confirmed"] is True

    def test_get_transaction_receipt_none(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_w3.eth.get_transaction_receipt.return_value = None
        client._w3 = mock_w3

        result = client.get_transaction_receipt("0xtxhash")
        assert result is None

    def test_get_transaction_receipt_exception(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_w3 = Mock()
        mock_w3.eth.get_transaction_receipt.side_effect = Exception("Error")
        client._w3 = mock_w3

        result = client.get_transaction_receipt("0xtxhash")
        assert result is None

    def test_wait_for_transaction_success(self):
        client = ethereum_rpc.EthereumRPCClient()
        mock_receipt = {"hash": "0xtxhash", "status": 1}
        client.get_transaction_receipt = Mock(return_value=mock_receipt)

        result = client.wait_for_transaction("0xtxhash", timeout=1, poll_interval=0.1)
        assert result == mock_receipt

    def test_wait_for_transaction_timeout(self):
        client = ethereum_rpc.EthereumRPCClient()
        client.get_transaction_receipt = Mock(return_value=None)

        result = client.wait_for_transaction("0xtxhash", timeout=0.2, poll_interval=0.1)
        assert result is None

    def test_health_check_connected(self):
        client = ethereum_rpc.EthereumRPCClient()
        client.get_block_number = Mock(return_value=100)
        client.get_gas_price = Mock(return_value={"gwei": 5.0})
        client._connected_url = "https://test.rpc"

        result = client.health_check()
        assert result["status"] == "connected"
        assert result["latest_block"] == 100
        assert result["gas_price_gwei"] == 5.0

    def test_health_check_disconnected(self):
        client = ethereum_rpc.EthereumRPCClient()
        client.get_block_number = Mock(side_effect=Exception("Error"))

        result = client.health_check()
        assert result["status"] == "disconnected"
        assert "error" in result


# ============================================================================
# Global Functions Tests
# ============================================================================

class TestGlobalFunctions:
    """Test global Ethereum RPC functions"""

    def test_get_ethereum_client_singleton(self):
        ethereum_rpc._client = None
        client1 = ethereum_rpc.get_ethereum_client()
        client2 = ethereum_rpc.get_ethereum_client()
        assert client1 is client2

    def test_get_ethereum_client_existing(self):
        mock_client = Mock()
        ethereum_rpc._client = mock_client
        client = ethereum_rpc.get_ethereum_client()
        assert client is mock_client
