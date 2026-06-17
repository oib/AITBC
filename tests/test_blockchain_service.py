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
            service = RPCBlockchainService("http://localhost:8006", timeout=30)
            assert service.rpc_url == "http://localhost:8006"
            mock_client_class.assert_called_once_with(base_url="http://localhost:8006", timeout=30)

    def test_get_block_by_height(self):
        """Test get block by height"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "height": 100,
            "hash": "0xblock100",
            "parent_hash": "0xblock99",
            "timestamp": 1234567890,
            "transactions": [{"hash": "0xtx1"}],
            "miner": "0xminer",
            "gas_used": 1000,
            "gas_limit": 2000,
        }
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            block = service.get_block(100)

            assert block.height == 100
            assert block.hash == "0xblock100"
            mock_client.get.assert_called_once_with("/rpc/blocks/100")

    def test_get_block_by_hash(self):
        """Test get block by hash"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "height": 100,
            "hash": "0xblockhash",
            "parent_hash": "0xparent",
            "timestamp": 1234567890,
            "transactions": [],
        }
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            block = service.get_block("0xblockhash")

            assert block.height == 100
            mock_client.get.assert_called_once_with("/rpc/block/0xblockhash")

    def test_get_block_with_missing_fields(self):
        """Test get block handles missing fields with defaults"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"height": 100, "hash": "0xblock", "parent_hash": "0xparent", "timestamp": 0}
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            block = service.get_block(100)

            assert block.transactions == []
            assert block.miner is None
            assert block.gas_used is None

    @patch("aitbc.blockchain.blockchain_service.logger")
    def test_get_block_error(self, mock_logger):
        """Test get block handles errors"""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")

            with pytest.raises(Exception):  # noqa: B017
                service.get_block(100)

            mock_logger.error.assert_called_once()

    def test_get_head_block(self):
        """Test get head block"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "height": 200,
            "hash": "0xhead",
            "parent_hash": "0xprev",
            "timestamp": 1234567890,
            "transactions": [],
        }
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            block = service.get_head_block()

            assert block.height == 200
            assert block.hash == "0xhead"
            mock_client.get.assert_called_once_with("/rpc/head")

    def test_get_transaction(self):
        """Test get transaction by hash"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "hash": "0xtx123",
            "from": "0xfrom",
            "to": "0xto",
            "value": "1000000000000000000",
            "nonce": 1,
            "gas": 21000,
            "gas_price": "1000000000",
            "input": "0xdata",
            "block_hash": "0xblock",
            "block_number": 100,
            "status": "success",
        }
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            tx = service.get_transaction("0xtx123")

            assert tx.hash == "0xtx123"
            assert tx.from_address == "0xfrom"
            assert tx.to_address == "0xto"
            mock_client.get.assert_called_once_with("/rpc/transaction/0xtx123")

    def test_get_transaction_with_missing_fields(self):
        """Test get transaction handles missing fields"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"hash": "0xtx", "from": "0xfrom", "to": "0xto", "value": "0", "nonce": 0, "gas": 0}
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            tx = service.get_transaction("0xtx")

            assert tx.gas_price is None
            assert tx.input_data is None
            assert tx.block_number is None

    def test_get_account_balance(self):
        """Test get account balance"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"balance": "1000000000000000000", "nonce": 5}
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            account = service.get_account_balance("0xaccount")

            assert account.address == "0xaccount"
            assert account.balance == 1000000000000000000
            assert account.nonce == 5
            mock_client.get.assert_called_once_with("/rpc/account/0xaccount")

    def test_get_account_balance_with_defaults(self):
        """Test get account balance with default values"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            account = service.get_account_balance("0xaccount")

            assert account.balance == 0
            assert account.nonce == 0

    def test_send_transaction(self):
        """Test send transaction"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"hash": "0xtxhash"}
        mock_client.post.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            tx_hash = service.send_transaction({"from": "0xfrom", "to": "0xto"})

            assert tx_hash == "0xtxhash"
            mock_client.post.assert_called_once_with("/rpc/sendTx", json={"from": "0xfrom", "to": "0xto"})

    def test_send_transaction_with_tx_hash_key(self):
        """Test send transaction with tx_hash key in response"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"tx_hash": "0xtxhash"}
        mock_client.post.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            tx_hash = service.send_transaction({})

            assert tx_hash == "0xtxhash"

    def test_send_transaction_no_hash_error(self):
        """Test send transaction raises error when no hash in response"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_client.post.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")

            with pytest.raises(ValueError, match="Transaction hash not found"):
                service.send_transaction({})

    def test_get_status(self):
        """Test get node status"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "syncing", "block_height": 100, "peers": 5}
        mock_client.get.return_value = mock_response

        with patch("aitbc.blockchain.blockchain_service.AITBCHTTPClient", return_value=mock_client):
            service = RPCBlockchainService("http://localhost:8006")
            status = service.get_status()

            assert status["status"] == "syncing"
            assert status["block_height"] == 100
            mock_client.get.assert_called_once_with("/rpc/status")


class TestBlockchainServiceFactory:
    """Tests for BlockchainServiceFactory"""

    def test_create_rpc_service(self):
        """Test create RPC service"""
        with patch("aitbc.blockchain.blockchain_service.RPCBlockchainService") as mock_service_class:
            factory = BlockchainServiceFactory()
            factory.create_rpc_service("http://localhost:8006", timeout=60)

            mock_service_class.assert_called_once_with("http://localhost:8006", 60)

    def test_create_service_rpc(self):
        """Test create service with RPC type"""
        with patch("aitbc.blockchain.blockchain_service.BlockchainServiceFactory.create_rpc_service") as mock_create:
            factory = BlockchainServiceFactory()
            factory.create_service("rpc", rpc_url="http://localhost:8006")

            mock_create.assert_called_once_with(rpc_url="http://localhost:8006")

    def test_create_service_unknown_type(self):
        """Test create service with unknown type raises error"""
        factory = BlockchainServiceFactory()

        with pytest.raises(ValueError, match="Unknown service type"):
            factory.create_service("unknown", rpc_url="http://localhost:8006")

    def test_create_service_default_kwargs(self):
        """Test create service passes kwargs correctly"""
        with patch("aitbc.blockchain.blockchain_service.BlockchainServiceFactory.create_rpc_service") as mock_create:
            factory = BlockchainServiceFactory()
            factory.create_service("rpc", rpc_url="http://localhost:8006", timeout=45)

            mock_create.assert_called_once_with(rpc_url="http://localhost:8006", timeout=45)


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
