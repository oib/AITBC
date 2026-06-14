"""Tests for aitbc.ethereum_rpc"""

from unittest.mock import MagicMock, patch

import pytest

from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient, get_ethereum_client


class TestEthereumConfig:
    def test_default_config(self):
        config = EthereumConfig()
        assert config.network == "sepolia"
        assert config.timeout == 10
        assert config.max_retries == 3

    def test_custom_config(self):
        config = EthereumConfig(network="mainnet", rpc_url="https://rpc.example.com", timeout=20)
        assert config.network == "mainnet"
        assert config.rpc_url == "https://rpc.example.com"
        assert config.timeout == 20

    def test_get_rpc_urls_custom(self):
        config = EthereumConfig(network="mainnet", rpc_url="https://custom.rpc")
        urls = config.get_rpc_urls()
        assert urls[0] == "https://custom.rpc"

    def test_get_rpc_urls_infura(self):
        config = EthereumConfig(network="mainnet", infura_key="test_key")
        urls = config.get_rpc_urls()
        assert any("infura.io" in u for u in urls)

    def test_get_rpc_urls_alchemy(self):
        config = EthereumConfig(network="mainnet", alchemy_key="test_key")
        urls = config.get_rpc_urls()
        assert any("alchemy.com" in u for u in urls)

    def test_get_rpc_urls_mainnet(self):
        config = EthereumConfig(network="mainnet")
        urls = config.get_rpc_urls()
        assert any("publicnode.com" in u for u in urls)

    def test_get_rpc_urls_sepolia(self):
        config = EthereumConfig(network="sepolia")
        urls = config.get_rpc_urls()
        assert any("sepolia" in u for u in urls)


class TestEthereumRPCClient:
    def test_init_default(self):
        client = EthereumRPCClient()
        assert client.config is not None
        assert client._w3 is None

    def test_init_custom_config(self):
        config = EthereumConfig(network="mainnet")
        client = EthereumRPCClient(config=config)
        assert client.config.network == "mainnet"

    def test_connected_url_none(self):
        client = EthereumRPCClient()
        assert client.connected_url is None

    def test_get_transaction_none(self):
        client = EthereumRPCClient()
        with patch.object(client, "_get_web3") as mock_get:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction.side_effect = Exception("not found")
            mock_get.return_value = mock_w3
            result = client.get_transaction("0xabc")
            assert result is None

    def test_get_transaction_receipt_none(self):
        client = EthereumRPCClient()
        with patch.object(client, "_get_web3") as mock_get:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_receipt.return_value = None
            mock_get.return_value = mock_w3
            result = client.get_transaction_receipt("0xabc")
            assert result is None

    def test_get_gas_price(self):
        client = EthereumRPCClient()
        with patch.object(client, "_get_web3") as mock_get:
            mock_w3 = MagicMock()
            mock_w3.eth.gas_price = 1000000000
            mock_get.return_value = mock_w3
            result = client.get_gas_price()
            assert result["wei"] == 1000000000

    def test_get_balance(self):
        client = EthereumRPCClient()
        with patch.object(client, "_get_web3") as mock_get:
            mock_w3 = MagicMock()
            mock_w3.eth.get_balance.return_value = 1000000000000000000
            mock_get.return_value = mock_w3
            result = client.get_balance("0x1234567890123456789012345678901234567890")
            assert result["wei"] == 1000000000000000000
            assert result["ether"] == 1.0

    def test_get_block(self):
        client = EthereumRPCClient()
        with patch.object(client, "_get_web3") as mock_get:
            mock_block = MagicMock()
            mock_block.number = 100
            mock_block.hash.hex.return_value = "0xabc"
            mock_block.timestamp = 1234567890
            mock_block.transactions = []
            mock_block.gasUsed = 100000
            mock_block.gasLimit = 15000000
            mock_w3 = MagicMock()
            mock_w3.eth.get_block.return_value = mock_block
            mock_get.return_value = mock_w3
            result = client.get_block("latest")
            assert result["number"] == 100
            assert result["gas_used"] == 100000

    def test_get_block_number(self):
        client = EthereumRPCClient()
        with patch.object(client, "_get_web3") as mock_get:
            mock_w3 = MagicMock()
            mock_w3.eth.block_number = 1000
            mock_get.return_value = mock_w3
            result = client.get_block_number()
            assert result == 1000

    def test_wait_for_transaction_timeout(self):
        client = EthereumRPCClient()
        with patch.object(client, "get_transaction_receipt", return_value=None):
            with patch("aitbc.ethereum_rpc.time") as mock_time:
                mock_time.time.side_effect = [0, 5, 10]
                result = client.wait_for_transaction("0xabc", timeout=8, poll_interval=5)
        assert result is None


class TestGlobalClient:
    def test_singleton(self):
        c1 = get_ethereum_client()
        c2 = get_ethereum_client()
        assert c1 is c2
