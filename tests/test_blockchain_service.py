"""
Tests for blockchain service layer
"""

from unittest.mock import MagicMock, patch

import pytest

from aitbc.blockchain.blockchain_service import (
    Account,
    Block,
    BlockchainService,
    BlockchainServiceFactory,
    RPCBlockchainService,
    Transaction,
)


class TestDataClasses:
    """Tests for blockchain data classes"""

    def test_block_creation(self):
        """Test Block dataclass creation"""
        block = Block(
            height=100,
            hash="0xabc123",
            parent_hash="0xdef456",
            timestamp=1234567890,
            transactions=[{"hash": "0xtx1"}],
            miner="0xminer",
            gas_used=1000,
            gas_limit=2000,
        )
        assert block.height == 100
        assert block.hash == "0xabc123"
        assert block.parent_hash == "0xdef456"
        assert block.transactions == [{"hash": "0xtx1"}]

    def test_block_optional_fields(self):
        """Test Block with optional fields None"""
        block = Block(height=1, hash="0xabc", parent_hash="0xdef", timestamp=0, transactions=[])
        assert block.miner is None
        assert block.gas_used is None
        assert block.gas_limit is None

    def test_transaction_creation(self):
        """Test Transaction dataclass creation"""
        tx = Transaction(
            hash="0xtx123",
            from_address="0xfrom",
            to_address="0xto",
            value="1000000000000000000",
            nonce=1,
            gas=21000,
            gas_price="1000000000",
            input_data="0xdata",
            block_hash="0xblock",
            block_number=100,
            status="success",
        )
        assert tx.hash == "0xtx123"
        assert tx.from_address == "0xfrom"
        assert tx.to_address == "0xto"

    def test_transaction_optional_fields(self):
        """Test Transaction with optional fields None"""
        tx = Transaction(hash="0xtx", from_address="0xfrom", to_address="0xto", value="0", nonce=0, gas=0)
        assert tx.gas_price is None
        assert tx.input_data is None
        assert tx.block_hash is None

    def test_account_creation(self):
        """Test Account dataclass creation"""
        account = Account(address="0xaccount123", balance=1000000000000000000, nonce=5)
        assert account.address == "0xaccount123"
        assert account.balance == 1000000000000000000
        assert account.nonce == 5


class TestRPCBlockchainService:
    """Tests for RPCBlockchainService"""

    def test_initialization(self):
        """Test RPCBlockchainService initialization"""
        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient") as mock_client_class:
            service = RPCBlockchainService("http://localhost:8202", timeout=30)
            assert service.rpc_url == "http://localhost:8202"
            mock_client_class.assert_called_once_with(base_url="http://localhost:8202", timeout=30)

    @patch("aitbc.blockchain.blockchain_service.logger")
    def test_get_block_error(self, mock_logger):
        """Test get block handles errors"""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8202")

            with pytest.raises(Exception):  # noqa: B017
                service.get_block(100)

            mock_logger.error.assert_called_once()


class TestBlockchainServiceFactory:
    """Tests for BlockchainServiceFactory"""

    def test_create_rpc_service(self):
        """Test create RPC service"""
        with patch("aitbc.blockchain.blockchain_service.RPCBlockchainService") as mock_service_class:
            factory = BlockchainServiceFactory()
            factory.create_rpc_service("http://localhost:8202", timeout=60)

            mock_service_class.assert_called_once_with("http://localhost:8202", 60)

    def test_create_service_rpc(self):
        """Test create service with RPC type"""
        with patch("aitbc.blockchain.blockchain_service.BlockchainServiceFactory.create_rpc_service") as mock_create:
            factory = BlockchainServiceFactory()
            factory.create_service("rpc", rpc_url="http://localhost:8202")

            mock_create.assert_called_once_with(rpc_url="http://localhost:8202")

    def test_create_service_unknown_type(self):
        """Test create service with unknown type raises error"""
        factory = BlockchainServiceFactory()

        with pytest.raises(ValueError, match="Unknown service type"):
            factory.create_service("unknown", rpc_url="http://localhost:8202")

    def test_create_service_default_kwargs(self):
        """Test create service passes kwargs correctly"""
        with patch("aitbc.blockchain.blockchain_service.BlockchainServiceFactory.create_rpc_service") as mock_create:
            factory = BlockchainServiceFactory()
            factory.create_service("rpc", rpc_url="http://localhost:8202", timeout=45)

            mock_create.assert_called_once_with(rpc_url="http://localhost:8202", timeout=45)


class TestBlockchainServiceAbstract:
    """Tests for BlockchainService abstract class"""

    def test_blockchain_service_is_abstract(self):
        """Test BlockchainService cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BlockchainService()

    def test_blockchain_service_has_abstract_methods(self):
        """Test BlockchainService defines required abstract methods"""
        assert hasattr(BlockchainService, "get_block")
        assert hasattr(BlockchainService, "get_head_block")
        assert hasattr(BlockchainService, "get_transaction")
        assert hasattr(BlockchainService, "get_account_balance")
        assert hasattr(BlockchainService, "send_transaction")
        assert hasattr(BlockchainService, "get_status")
