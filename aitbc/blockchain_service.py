"""
Blockchain service layer for AITBC
Provides high-level blockchain interaction services with abstraction over RPC calls
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.network.http_client import AITBCHTTPClient

logger = get_logger(__name__)


@dataclass
class Block:
    """Block data structure"""
    height: int
    hash: str
    parent_hash: str
    timestamp: int
    transactions: list[dict[str, Any]]
    miner: str | None = None
    gas_used: int | None = None
    gas_limit: int | None = None


@dataclass
class Transaction:
    """Transaction data structure"""
    hash: str
    from_address: str
    to_address: str
    value: str
    nonce: int
    gas: int
    gas_price: str | None = None
    input_data: str | None = None
    block_hash: str | None = None
    block_number: int | None = None
    status: str | None = None


@dataclass
class Account:
    """Account data structure"""
    address: str
    balance: int
    nonce: int


class BlockchainService(ABC):
    """Abstract base class for blockchain service implementations"""

    @abstractmethod
    def get_block(self, block_identifier: int | str) -> Block:
        """Get block by height or hash"""
        pass

    @abstractmethod
    def get_head_block(self) -> Block:
        """Get current head block"""
        pass

    @abstractmethod
    def get_transaction(self, tx_hash: str) -> Transaction:
        """Get transaction by hash"""
        pass

    @abstractmethod
    def get_account_balance(self, address: str) -> Account:
        """Get account information including balance"""
        pass

    @abstractmethod
    def send_transaction(self, tx_data: dict[str, Any]) -> str:
        """Send transaction and return transaction hash"""
        pass

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Get blockchain node status"""
        pass


class RPCBlockchainService(BlockchainService):
    """RPC-based blockchain service implementation"""

    def __init__(self, rpc_url: str, timeout: int = 30):
        """
        Initialize RPC blockchain service

        Args:
            rpc_url: Blockchain RPC endpoint URL
            timeout: Request timeout in seconds
        """
        self.rpc_url = rpc_url
        self.client = AITBCHTTPClient(base_url=rpc_url, timeout=timeout)
        logger.info(f"Initialized RPC blockchain service for {rpc_url}")

    def get_block(self, block_identifier: int | str) -> Block:
        """
        Get block by height or hash

        Args:
            block_identifier: Block height (int) or hash (str)

        Returns:
            Block object with block data

        Raises:
            ValueError: If block not found
            NetworkError: If RPC call fails
        """
        try:
            if isinstance(block_identifier, int):
                endpoint = f"/rpc/blocks/{block_identifier}"
            else:
                endpoint = f"/rpc/block/{block_identifier}"

            response = self.client.get(endpoint)
            data = response.json()

            return Block(
                height=data.get("height", 0),
                hash=data.get("hash", ""),
                parent_hash=data.get("parent_hash", ""),
                timestamp=data.get("timestamp", 0),
                transactions=data.get("transactions", []),
                miner=data.get("miner"),
                gas_used=data.get("gas_used"),
                gas_limit=data.get("gas_limit")
            )
        except Exception as e:
            logger.error(f"Failed to get block {block_identifier}: {e}")
            raise

    def get_head_block(self) -> Block:
        """
        Get current head block

        Returns:
            Block object with head block data

        Raises:
            NetworkError: If RPC call fails
        """
        try:
            response = self.client.get("/rpc/head")
            data = response.json()

            return Block(
                height=data.get("height", 0),
                hash=data.get("hash", ""),
                parent_hash=data.get("parent_hash", ""),
                timestamp=data.get("timestamp", 0),
                transactions=data.get("transactions", []),
                miner=data.get("miner"),
                gas_used=data.get("gas_used"),
                gas_limit=data.get("gas_limit")
            )
        except Exception as e:
            logger.error(f"Failed to get head block: {e}")
            raise

    def get_transaction(self, tx_hash: str) -> Transaction:
        """
        Get transaction by hash

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction object with transaction data

        Raises:
            ValueError: If transaction not found
            NetworkError: If RPC call fails
        """
        try:
            response = self.client.get(f"/rpc/transaction/{tx_hash}")
            data = response.json()

            return Transaction(
                hash=data.get("hash", ""),
                from_address=data.get("from", ""),
                to_address=data.get("to", ""),
                value=data.get("value", "0"),
                nonce=data.get("nonce", 0),
                gas=data.get("gas", 0),
                gas_price=data.get("gas_price"),
                input_data=data.get("input"),
                block_hash=data.get("block_hash"),
                block_number=data.get("block_number"),
                status=data.get("status")
            )
        except Exception as e:
            logger.error(f"Failed to get transaction {tx_hash}: {e}")
            raise

    def get_account_balance(self, address: str) -> Account:
        """
        Get account information including balance

        Args:
            address: Account address

        Returns:
            Account object with account data

        Raises:
            ValueError: If address is invalid
            NetworkError: If RPC call fails
        """
        try:
            response = self.client.get(f"/rpc/account/{address}")
            data = response.json()

            return Account(
                address=address,
                balance=int(data.get("balance", 0)),
                nonce=data.get("nonce", 0)
            )
        except Exception as e:
            logger.error(f"Failed to get account balance for {address}: {e}")
            raise

    def send_transaction(self, tx_data: dict[str, Any]) -> str:
        """
        Send transaction and return transaction hash

        Args:
            tx_data: Transaction data dictionary

        Returns:
            Transaction hash

        Raises:
            ValueError: If transaction data is invalid
            NetworkError: If RPC call fails
        """
        try:
            response = self.client.post("/rpc/sendTx", json=tx_data)
            data = response.json()

            tx_hash = data.get("hash") or data.get("tx_hash")
            if not tx_hash:
                raise ValueError("Transaction hash not found in response")

            logger.info(f"Transaction sent successfully: {tx_hash}")
            return tx_hash
        except Exception as e:
            logger.error(f"Failed to send transaction: {e}")
            raise

    def get_status(self) -> dict[str, Any]:
        """
        Get blockchain node status

        Returns:
            Dictionary with node status information

        Raises:
            NetworkError: If RPC call fails
        """
        try:
            response = self.client.get("/rpc/status")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get node status: {e}")
            raise


class BlockchainServiceFactory:
    """Factory for creating blockchain service instances"""

    @staticmethod
    def create_rpc_service(rpc_url: str, timeout: int = 30) -> RPCBlockchainService:
        """
        Create RPC blockchain service

        Args:
            rpc_url: Blockchain RPC endpoint URL
            timeout: Request timeout in seconds

        Returns:
            RPCBlockchainService instance
        """
        return RPCBlockchainService(rpc_url, timeout)

    @staticmethod
    def create_service(service_type: str = "rpc", **kwargs) -> BlockchainService:
        """
        Create blockchain service by type

        Args:
            service_type: Type of service ("rpc")
            **kwargs: Service-specific configuration

        Returns:
            BlockchainService instance

        Raises:
            ValueError: If service type is unknown
        """
        if service_type == "rpc":
            return BlockchainServiceFactory.create_rpc_service(**kwargs)
        else:
            raise ValueError(f"Unknown service type: {service_type}")
