"""Tests for AITBC blockchain module.

Tests cover:
- Block, Transaction, Account dataclasses
- BlockchainService abstract base class
- RPCBlockchainService implementation
- BlockchainServiceFactory
"""

from unittest.mock import Mock, patch

import pytest

# Import from modules directly since not all are exported from __init__.py
from aitbc.blockchain import (
    BlockchainService,
    BlockchainServiceFactory,
    RPCBlockchainService,
)
from aitbc.blockchain.blockchain_service import (
    Account,
    Block,
    Transaction,
)


class TestBlock:
    """Test Block dataclass."""

    def test_block_creation_minimal(self):
        """Test Block creation with required fields."""
        block = Block(
            height=100,
            hash="0xabc123",
            parent_hash="0xdef456",
            timestamp=1234567890,
            transactions=[{"hash": "tx1"}],
        )
        assert block.height == 100
        assert block.hash == "0xabc123"
        assert block.parent_hash == "0xdef456"
        assert block.timestamp == 1234567890
        assert block.transactions == [{"hash": "tx1"}]
        assert block.miner is None
        assert block.gas_used is None
        assert block.gas_limit is None

    def test_block_creation_full(self):
        """Test Block creation with all fields."""
        block = Block(
            height=200,
            hash="0xhash123",
            parent_hash="0xparent456",
            timestamp=9876543210,
            transactions=[{"hash": "tx1"}, {"hash": "tx2"}],
            miner="0xminer",
            gas_used=100000,
            gas_limit=200000,
        )
        assert block.miner == "0xminer"
        assert block.gas_used == 100000
        assert block.gas_limit == 200000


class TestTransaction:
    """Test Transaction dataclass."""

    def test_transaction_creation_minimal(self):
        """Test Transaction creation with required fields."""
        tx = Transaction(
            hash="0xtx123",
            from_address="0xfrom",
            to_address="0xto",
            value="1000000",
            nonce=1,
            gas=21000,
        )
        assert tx.hash == "0xtx123"
        assert tx.from_address == "0xfrom"
        assert tx.to_address == "0xto"
        assert tx.value == "1000000"
        assert tx.nonce == 1
        assert tx.gas == 21000
        assert tx.gas_price is None
        assert tx.input_data is None
        assert tx.block_hash is None
        assert tx.block_number is None
        assert tx.status is None

    def test_transaction_creation_full(self):
        """Test Transaction creation with all fields."""
        tx = Transaction(
            hash="0xtx456",
            from_address="0xfrom",
            to_address="0xto",
            value="500000",
            nonce=5,
            gas=100000,
            gas_price="20000000000",
            input_data="0xdata",
            block_hash="0xblock",
            block_number=100,
            status="confirmed",
        )
        assert tx.gas_price == "20000000000"
        assert tx.input_data == "0xdata"
        assert tx.block_hash == "0xblock"
        assert tx.block_number == 100
        assert tx.status == "confirmed"


class TestAccount:
    """Test Account dataclass."""

    def test_account_creation(self):
        """Test Account creation."""
        account = Account(
            address="0xaccount",
            balance=1000000000000000000,
            nonce=10,
        )
        assert account.address == "0xaccount"
        assert account.balance == 1000000000000000000
        assert account.nonce == 10


class TestRPCBlockchainService:
    """Test RPCBlockchainService class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock HTTP client."""
        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient") as mock_class:
            mock_http = Mock()
            mock_class.return_value = mock_http
            service = RPCBlockchainService(rpc_url="http://localhost:8080", timeout=30)
            return service, mock_http

    def test_service_initialization(self):
        """Test service initialization."""
        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient"):
            service = RPCBlockchainService(rpc_url="http://localhost:8080", timeout=60)
            assert service.rpc_url == "http://localhost:8080"
            assert service.client is not None

    def test_get_block_by_height(self, mock_client):
        """Test get_block with block height (int)."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {
            "height": 100,
            "hash": "0xblockhash",
            "parent_hash": "0xparent",
            "timestamp": 1234567890,
            "transactions": [{"hash": "tx1"}],
            "miner": "0xminer",
            "gas_used": 100000,
            "gas_limit": 200000,
        }
        mock_http.get.return_value = mock_response

        block = service.get_block(100)

        assert isinstance(block, Block)
        assert block.height == 100
        assert block.hash == "0xblockhash"
        assert block.miner == "0xminer"
        mock_http.get.assert_called_once_with("/rpc/blocks/100")

    def test_get_block_by_hash(self, mock_client):
        """Test get_block with block hash (str)."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {
            "height": 100,
            "hash": "0xblockhash",
            "parent_hash": "0xparent",
            "timestamp": 1234567890,
            "transactions": [],
        }
        mock_http.get.return_value = mock_response

        block = service.get_block("0xblockhash")

        assert block.height == 100
        mock_http.get.assert_called_once_with("/rpc/block/0xblockhash")

    def test_get_block_error(self, mock_client):
        """Test get_block error handling."""
        service, mock_http = mock_client
        mock_http.get.side_effect = Exception("RPC Error")

        with pytest.raises(Exception, match="RPC Error"):
            service.get_block(100)

    def test_get_head_block(self, mock_client):
        """Test get_head_block."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {
            "height": 500,
            "hash": "0xheadhash",
            "parent_hash": "0xparent",
            "timestamp": 1234567890,
            "transactions": [{"hash": "tx1"}],
            "miner": "0xminer",
            "gas_used": 50000,
            "gas_limit": 100000,
        }
        mock_http.get.return_value = mock_response

        block = service.get_head_block()

        assert block.height == 500
        mock_http.get.assert_called_once_with("/rpc/head")

    def test_get_transaction(self, mock_client):
        """Test get_transaction."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {
            "hash": "0xtx123",
            "from": "0xfrom",
            "to": "0xto",
            "value": "1000000",
            "nonce": 1,
            "gas": 21000,
            "gas_price": "20000000000",
            "input": "0xdata",
            "block_hash": "0xblock",
            "block_number": 100,
            "status": "confirmed",
        }
        mock_http.get.return_value = mock_response

        tx = service.get_transaction("0xtx123")

        assert isinstance(tx, Transaction)
        assert tx.hash == "0xtx123"
        assert tx.from_address == "0xfrom"
        assert tx.to_address == "0xto"
        assert tx.value == "1000000"
        assert tx.gas_price == "20000000000"
        mock_http.get.assert_called_once_with("/rpc/transaction/0xtx123")

    def test_get_account_balance(self, mock_client):
        """Test get_account_balance."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {
            "balance": "1000000000000000000",
            "nonce": 10,
        }
        mock_http.get.return_value = mock_response

        account = service.get_account_balance("0xaccount")

        assert isinstance(account, Account)
        assert account.address == "0xaccount"
        assert account.balance == 1000000000000000000
        assert account.nonce == 10
        mock_http.get.assert_called_once_with("/rpc/account/0xaccount")

    def test_send_transaction(self, mock_client):
        """Test send_transaction."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {"hash": "0xtxhash"}
        mock_http.post.return_value = mock_response

        tx_hash = service.send_transaction({"from": "0xfrom", "to": "0xto", "value": "100"})

        assert tx_hash == "0xtxhash"
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert call_args[0][0] == "/rpc/sendTx"

    def test_send_transaction_no_hash(self, mock_client):
        """Test send_transaction when hash not in response."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {"success": True}  # No hash
        mock_http.post.return_value = mock_response

        with pytest.raises(ValueError, match="Transaction hash not found"):
            service.send_transaction({"from": "0xfrom"})

    def test_get_status(self, mock_client):
        """Test get_status."""
        service, mock_http = mock_client
        mock_response = Mock()
        mock_response.json.return_value = {
            "height": 1000,
            "chain_id": "testnet",
            "peers": 5,
        }
        mock_http.get.return_value = mock_response

        status = service.get_status()

        assert status["height"] == 1000
        assert status["chain_id"] == "testnet"
        mock_http.get.assert_called_once_with("/rpc/status")

    def test_error_handling(self, mock_client):
        """Test error handling propagates exceptions."""
        service, mock_http = mock_client
        mock_http.get.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            service.get_block(100)


class TestBlockchainServiceFactory:
    """Test BlockchainServiceFactory class."""

    def test_create_rpc_service(self):
        """Test create_rpc_service factory method."""
        with patch("aitbc.blockchain.blockchain_service.RPCBlockchainService") as mock_class:
            mock_instance = Mock()
            mock_class.return_value = mock_instance

            service = BlockchainServiceFactory.create_rpc_service("http://localhost:8080", timeout=45)

            assert service is mock_instance
            mock_class.assert_called_once_with("http://localhost:8080", 45)

    def test_create_service_rpc(self):
        """Test create_service with RPC type."""
        with patch.object(BlockchainServiceFactory, "create_rpc_service") as mock_create:
            mock_service = Mock()
            mock_create.return_value = mock_service

            service = BlockchainServiceFactory.create_service("rpc", rpc_url="http://test")

            assert service is mock_service
            mock_create.assert_called_once_with(rpc_url="http://test")

    def test_create_service_unknown_type(self):
        """Test create_service with unknown type."""
        with pytest.raises(ValueError, match="Unknown service type: unknown"):
            BlockchainServiceFactory.create_service("unknown")


class TestBlockchainService:
    """Test BlockchainService abstract base class."""

    def test_cannot_instantiate_abstract(self):
        """Test that BlockchainService cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BlockchainService()

    def test_abstract_methods_defined(self):
        """Test that all abstract methods are defined."""
        abstract_methods = BlockchainService.__abstractmethods__
        assert "get_block" in abstract_methods
        assert "get_head_block" in abstract_methods
        assert "get_transaction" in abstract_methods
        assert "get_account_balance" in abstract_methods
        assert "send_transaction" in abstract_methods
        assert "get_status" in abstract_methods


class TestBlockchainServiceIntegration:
    """Integration tests for blockchain service."""

    def test_factory_creates_rpc_service(self):
        """Test factory creates RPC service correctly."""
        with patch("aitbc.blockchain.blockchain_service.RPCBlockchainService") as mock_class:
            mock_instance = Mock()
            mock_class.return_value = mock_instance

            service = BlockchainServiceFactory.create_service("rpc", rpc_url="http://test:8080", timeout=60)

            assert service is mock_instance
            mock_class.assert_called_once_with("http://test:8080", 60)

    @patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient")
    def test_full_mock_flow(self, mock_http_class):
        """Test full flow with mocked HTTP client."""
        mock_http = Mock()
        mock_http_class.return_value = mock_http

        mock_response = Mock()
        mock_response.json.return_value = {
            "height": 100,
            "hash": "0xhash",
            "parent_hash": "0xparent",
            "timestamp": 1234567890,
            "transactions": [],
        }
        mock_http.get.return_value = mock_response

        service = RPCBlockchainService("http://localhost:8080")
        block = service.get_block(100)

        assert block.height == 100
        assert block.hash == "0xhash"
        mock_http.get.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
