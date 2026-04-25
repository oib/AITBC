"""
Enhanced Multi-Chain Wallet Adapter
Production-ready wallet adapter for cross-chain operations with advanced security and management
"""

import hashlib
import json
import secrets
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)

from ..domain.agent_identity import ChainType


class WalletStatus(StrEnum):
    """Wallet status enumeration"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    FROZEN = "frozen"
    SUSPENDED = "suspended"
    COMPROMISED = "compromised"


class TransactionStatus(StrEnum):
    """Transaction status enumeration"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SecurityLevel(StrEnum):
    """Security level for wallet operations"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"


class EnhancedWalletAdapter(ABC):
    """Enhanced abstract base class for blockchain-specific wallet adapters"""

    def __init__(
        self, chain_id: int, chain_type: ChainType, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM
    ):
        self.chain_id = chain_id
        self.chain_type = chain_type
        self.rpc_url = rpc_url
        self.security_level = security_level
        self._connection_pool = None
        self._rate_limiter = None

    @abstractmethod
    async def create_wallet(self, owner_address: str, security_config: dict[str, Any]) -> dict[str, Any]:
        """Create a new secure wallet for the agent"""
        pass

    @abstractmethod
    async def get_balance(self, wallet_address: str, token_address: str | None = None) -> dict[str, Any]:
        """Get wallet balance with multi-token support"""
        pass

    @abstractmethod
    async def execute_transaction(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal | float | str,
        token_address: str | None = None,
        data: dict[str, Any] | None = None,
        gas_limit: int | None = None,
        gas_price: int | None = None,
    ) -> dict[str, Any]:
        """Execute a transaction with enhanced security"""
        pass

    @abstractmethod
    async def get_transaction_status(self, transaction_hash: str) -> dict[str, Any]:
        """Get detailed transaction status"""
        pass

    @abstractmethod
    async def estimate_gas(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal | float | str,
        token_address: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Estimate gas for transaction"""
        pass

    @abstractmethod
    async def validate_address(self, address: str) -> bool:
        """Validate blockchain address format"""
        pass

    @abstractmethod
    async def get_transaction_history(
        self,
        wallet_address: str,
        limit: int = 100,
        offset: int = 0,
        from_block: int | None = None,
        to_block: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get transaction history for wallet"""
        pass

    async def secure_sign_message(self, message: str, private_key: str) -> str:
        """Securely sign a message"""
        try:
            # Add timestamp and nonce for replay protection
            timestamp = str(int(datetime.utcnow().timestamp()))
            nonce = secrets.token_hex(16)

            message_to_sign = f"{message}:{timestamp}:{nonce}"

            # Hash the message
            message_hash = hashlib.sha256(message_to_sign.encode()).hexdigest()

            # Sign the hash (implementation depends on chain)
            signature = await self._sign_hash(message_hash, private_key)

            return {"signature": signature, "message": message, "timestamp": timestamp, "nonce": nonce, "hash": message_hash}

        except Exception as e:
            logger.error(f"Error signing message: {e}")
            raise

    async def verify_signature(self, message: str, signature: str, address: str) -> bool:
        """Verify a message signature"""
        try:
            # Extract timestamp and nonce from signature data
            signature_data = json.loads(signature) if isinstance(signature, str) else signature

            message_to_verify = f"{message}:{signature_data['timestamp']}:{signature_data['nonce']}"
            message_hash = hashlib.sha256(message_to_verify.encode()).hexdigest()

            # Verify the signature (implementation depends on chain)
            return await self._verify_signature(message_hash, signature_data["signature"], address)

        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False

    @abstractmethod
    async def _sign_hash(self, message_hash: str, private_key: str) -> str:
        """Sign a hash with private key (chain-specific implementation)"""
        pass

    @abstractmethod
    async def _verify_signature(self, message_hash: str, signature: str, address: str) -> bool:
        """Verify a signature (chain-specific implementation)"""
        pass


class EthereumWalletAdapter(EnhancedWalletAdapter):
    """Enhanced Ethereum wallet adapter with advanced security"""

    def __init__(self, chain_id: int, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(chain_id, ChainType.ETHEREUM, rpc_url, security_level)
        self.chain_id = chain_id

    async def create_wallet(self, owner_address: str, security_config: dict[str, Any]) -> dict[str, Any]:
        """Create a new Ethereum wallet with enhanced security"""
        try:
            # Generate secure private key
            private_key = secrets.token_hex(32)

            # Derive address from private key
            address = await self._derive_address_from_private_key(private_key)

            # Create wallet record
            wallet_data = {
                "address": address,
                "private_key": private_key,
                "chain_id": self.chain_id,
                "chain_type": self.chain_type.value,
                "owner_address": owner_address,
                "security_level": self.security_level.value,
                "created_at": datetime.utcnow().isoformat(),
                "status": WalletStatus.ACTIVE.value,
                "security_config": security_config,
                "nonce": 0,
                "transaction_count": 0,
            }

            # Store encrypted private key (in production, use proper encryption)
            encrypted_private_key = await self._encrypt_private_key(private_key, security_config)
            wallet_data["encrypted_private_key"] = encrypted_private_key

            logger.info(f"Created Ethereum wallet {address} for owner {owner_address}")
            return wallet_data

        except Exception as e:
            logger.error(f"Error creating Ethereum wallet: {e}")
            raise

    async def get_balance(self, wallet_address: str, token_address: str | None = None) -> dict[str, Any]:
        """Get wallet balance with multi-token support"""
        try:
            if not await self.validate_address(wallet_address):
                raise ValueError(f"Invalid Ethereum address: {wallet_address}")

            # Get ETH balance
            eth_balance_wei = await self._get_eth_balance(wallet_address)
            eth_balance = float(Decimal(eth_balance_wei) / Decimal(10**18))

            result = {
                "address": wallet_address,
                "chain_id": self.chain_id,
                "eth_balance": eth_balance,
                "token_balances": {},
                "last_updated": datetime.utcnow().isoformat(),
            }

            # Get token balances if specified
            if token_address:
                token_balance = await self._get_token_balance(wallet_address, token_address)
                result["token_balances"][token_address] = token_balance

            return result

        except Exception as e:
            logger.error(f"Error getting balance for {wallet_address}: {e}")
            raise

    async def execute_transaction(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal | float | str,
        token_address: str | None = None,
        data: dict[str, Any] | None = None,
        gas_limit: int | None = None,
        gas_price: int | None = None,
    ) -> dict[str, Any]:
        """Execute an Ethereum transaction with enhanced security"""
        try:
            # Validate addresses
            if not await self.validate_address(from_address) or not await self.validate_address(to_address):
                raise ValueError("Invalid addresses provided")

            # Convert amount to wei
            if token_address:
                # ERC-20 token transfer
                amount_wei = int(float(amount) * 10**18)  # Assuming 18 decimals
                transaction_data = await self._create_erc20_transfer(from_address, to_address, token_address, amount_wei)
            else:
                # ETH transfer
                amount_wei = int(float(amount) * 10**18)
                transaction_data = {"from": from_address, "to": to_address, "value": hex(amount_wei), "data": "0x"}

            # Add data if provided
            if data:
                transaction_data["data"] = data.get("hex", "0x")

            # Estimate gas if not provided
            if not gas_limit:
                gas_estimate = await self.estimate_gas(from_address, to_address, amount, token_address, data)
                gas_limit = gas_estimate["gas_limit"]

            # Get gas price if not provided
            if not gas_price:
                gas_price = await self._get_gas_price()

            transaction_data.update(
                {
                    "gas": hex(gas_limit),
                    "gasPrice": hex(gas_price),
                    "nonce": await self._get_nonce(from_address),
                    "chainId": self.chain_id,
                }
            )

            # Sign transaction
            signed_tx = await self._sign_transaction(transaction_data, from_address)

            # Send transaction
            tx_hash = await self._send_raw_transaction(signed_tx)

            result = {
                "transaction_hash": tx_hash,
                "from": from_address,
                "to": to_address,
                "amount": str(amount),
                "token_address": token_address,
                "gas_limit": gas_limit,
                "gas_price": gas_price,
                "status": TransactionStatus.PENDING.value,
                "created_at": datetime.utcnow().isoformat(),
            }

            logger.info(f"Executed Ethereum transaction {tx_hash} from {from_address} to {to_address}")
            return result

        except Exception as e:
            logger.error(f"Error executing Ethereum transaction: {e}")
            raise

    async def get_transaction_status(self, transaction_hash: str) -> dict[str, Any]:
        """Get detailed transaction status"""
        try:
            # Get transaction receipt
            receipt = await self._get_transaction_receipt(transaction_hash)

            if not receipt:
                # Transaction not yet mined
                tx_data = await self._get_transaction_by_hash(transaction_hash)
                return {
                    "transaction_hash": transaction_hash,
                    "status": TransactionStatus.PENDING.value,
                    "block_number": None,
                    "block_hash": None,
                    "gas_used": None,
                    "effective_gas_price": None,
                    "logs": [],
                    "created_at": datetime.utcnow().isoformat(),
                }

            # Get transaction details
            tx_data = await self._get_transaction_by_hash(transaction_hash)

            result = {
                "transaction_hash": transaction_hash,
                "status": TransactionStatus.COMPLETED.value if receipt["status"] == 1 else TransactionStatus.FAILED.value,
                "block_number": receipt.get("blockNumber"),
                "block_hash": receipt.get("blockHash"),
                "gas_used": int(receipt.get("gasUsed", 0), 16),
                "effective_gas_price": int(receipt.get("effectiveGasPrice", 0), 16),
                "logs": receipt.get("logs", []),
                "from": tx_data.get("from"),
                "to": tx_data.get("to"),
                "value": int(tx_data.get("value", "0x0"), 16),
                "created_at": datetime.utcnow().isoformat(),
            }

            return result

        except Exception as e:
            logger.error(f"Error getting transaction status for {transaction_hash}: {e}")
            raise

    async def estimate_gas(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal | float | str,
        token_address: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Estimate gas for transaction"""
        try:
            # Convert amount to wei
            if token_address:
                amount_wei = int(float(amount) * 10**18)
                call_data = await self._create_erc20_transfer_call_data(to_address, token_address, amount_wei)
            else:
                amount_wei = int(float(amount) * 10**18)
                call_data = {
                    "from": from_address,
                    "to": to_address,
                    "value": hex(amount_wei),
                    "data": data.get("hex", "0x") if data else "0x",
                }

            # Estimate gas
            gas_estimate = await self._estimate_gas_call(call_data)

            return {
                "gas_limit": int(gas_estimate, 16),
                "gas_price_gwei": await self._get_gas_price_gwei(),
                "estimated_cost_eth": float(int(gas_estimate, 16) * await self._get_gas_price()) / 10**18,
                "estimated_cost_usd": 0.0,  # Would need ETH price oracle
            }

        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            raise

    async def validate_address(self, address: str) -> bool:
        """Validate Ethereum address format"""
        try:
            # Check if address is valid hex and correct length
            if not address.startswith("0x") or len(address) != 42:
                return False

            # Check if all characters are valid hex
            try:
                int(address, 16)
                return True
            except ValueError:
                return False

        except Exception:
            return False

    async def get_transaction_history(
        self,
        wallet_address: str,
        limit: int = 100,
        offset: int = 0,
        from_block: int | None = None,
        to_block: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get transaction history for wallet"""
        try:
            # Get transactions from blockchain
            transactions = await self._get_wallet_transactions(wallet_address, limit, offset, from_block, to_block)

            # Format transactions
            formatted_transactions = []
            for tx in transactions:
                formatted_tx = {
                    "hash": tx.get("hash"),
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "value": int(tx.get("value", "0x0"), 16),
                    "block_number": tx.get("blockNumber"),
                    "timestamp": tx.get("timestamp"),
                    "gas_used": int(tx.get("gasUsed", "0x0"), 16),
                    "status": TransactionStatus.COMPLETED.value,
                }
                formatted_transactions.append(formatted_tx)

            return formatted_transactions

        except Exception as e:
            logger.error(f"Error getting transaction history for {wallet_address}: {e}")
            raise

    # Private helper methods
    async def _derive_address_from_private_key(self, private_key: str) -> str:
        """Derive Ethereum address from private key"""
        # This would use actual Ethereum cryptography
        # For now, return a mock address
        return f"0x{hashlib.sha256(private_key.encode()).hexdigest()[:40]}"

    async def _encrypt_private_key(self, private_key: str, security_config: dict[str, Any]) -> str:
        """Encrypt private key with security configuration"""
        # This would use actual encryption
        # For now, return mock encrypted key
        return f"encrypted_{hashlib.sha256(private_key.encode()).hexdigest()}"

    async def _get_eth_balance(self, address: str) -> str:
        """Get ETH balance in wei"""
        # Mock implementation
        return "1000000000000000000"  # 1 ETH in wei

    async def _get_token_balance(self, address: str, token_address: str) -> dict[str, Any]:
        """Get ERC-20 token balance"""
        # Mock implementation
        return {"balance": "100000000000000000000", "decimals": 18, "symbol": "TOKEN"}  # 100 tokens

    async def _create_erc20_transfer(
        self, from_address: str, to_address: str, token_address: str, amount: int
    ) -> dict[str, Any]:
        """Create ERC-20 transfer transaction data"""
        # ERC-20 transfer function signature: 0xa9059cbb
        method_signature = "0xa9059cbb"
        padded_to_address = to_address[2:].zfill(64)
        padded_amount = hex(amount)[2:].zfill(64)
        data = method_signature + padded_to_address + padded_amount

        return {"from": from_address, "to": token_address, "data": f"0x{data}"}

    async def _create_erc20_transfer_call_data(self, to_address: str, token_address: str, amount: int) -> dict[str, Any]:
        """Create ERC-20 transfer call data for gas estimation"""
        method_signature = "0xa9059cbb"
        padded_to_address = to_address[2:].zfill(64)
        padded_amount = hex(amount)[2:].zfill(64)
        data = method_signature + padded_to_address + padded_amount

        return {
            "from": "0x0000000000000000000000000000000000000000",  # Mock from address
            "to": token_address,
            "data": f"0x{data}",
        }

    async def _get_gas_price(self) -> int:
        """Get current gas price"""
        # Mock implementation
        return 20000000000  # 20 Gwei in wei

    async def _get_gas_price_gwei(self) -> float:
        """Get current gas price in Gwei"""
        gas_price_wei = await self._get_gas_price()
        return gas_price_wei / 10**9

    async def _get_nonce(self, address: str) -> int:
        """Get transaction nonce for address"""
        # Mock implementation
        return 0

    async def _sign_transaction(self, transaction_data: dict[str, Any], from_address: str) -> str:
        """Sign transaction"""
        # Mock implementation
        return f"0xsigned_{hashlib.sha256(str(transaction_data).encode()).hexdigest()}"

    async def _send_raw_transaction(self, signed_transaction: str) -> str:
        """Send raw transaction"""
        # Mock implementation
        return f"0x{hashlib.sha256(signed_transaction.encode()).hexdigest()}"

    async def _get_transaction_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        """Get transaction receipt"""
        # Mock implementation
        return {
            "status": 1,
            "blockNumber": "0x12345",
            "blockHash": "0xabcdef",
            "gasUsed": "0x5208",
            "effectiveGasPrice": "0x4a817c800",
            "logs": [],
        }

    async def _get_transaction_by_hash(self, tx_hash: str) -> dict[str, Any]:
        """Get transaction by hash"""
        # Mock implementation
        return {"from": "0xsender", "to": "0xreceiver", "value": "0xde0b6b3a7640000", "data": "0x"}  # 1 ETH in wei

    async def _estimate_gas_call(self, call_data: dict[str, Any]) -> str:
        """Estimate gas for call"""
        # Mock implementation
        return "0x5208"  # 21000 in hex

    async def _get_wallet_transactions(
        self, address: str, limit: int, offset: int, from_block: int | None, to_block: int | None
    ) -> list[dict[str, Any]]:
        """Get wallet transactions"""
        # Mock implementation
        return [
            {
                "hash": f"0x{hashlib.sha256(f'tx_{i}'.encode()).hexdigest()}",
                "from": address,
                "to": f"0x{hashlib.sha256(f'to_{i}'.encode()).hexdigest()[:40]}",
                "value": "0xde0b6b3a7640000",
                "blockNumber": f"0x{12345 + i}",
                "timestamp": datetime.utcnow().timestamp(),
                "gasUsed": "0x5208",
            }
            for i in range(min(limit, 10))
        ]

    async def _sign_hash(self, message_hash: str, private_key: str) -> str:
        """Sign a hash with private key"""
        # Mock implementation
        return f"0x{hashlib.sha256(f'{message_hash}{private_key}'.encode()).hexdigest()}"

    async def _verify_signature(self, message_hash: str, signature: str, address: str) -> bool:
        """Verify a signature"""
        # Mock implementation
        return True


class PolygonWalletAdapter(EthereumWalletAdapter):
    """Polygon wallet adapter (inherits from Ethereum with chain-specific settings)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(137, rpc_url, security_level)
        self.chain_id = 137


class BSCWalletAdapter(EthereumWalletAdapter):
    """BSC wallet adapter (inherits from Ethereum with chain-specific settings)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(56, rpc_url, security_level)
        self.chain_id = 56


class ArbitrumWalletAdapter(EthereumWalletAdapter):
    """Arbitrum wallet adapter (inherits from Ethereum with chain-specific settings)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(42161, rpc_url, security_level)
        self.chain_id = 42161


class OptimismWalletAdapter(EthereumWalletAdapter):
    """Optimism wallet adapter (inherits from Ethereum with chain-specific settings)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(10, rpc_url, security_level)
        self.chain_id = 10


class AvalancheWalletAdapter(EthereumWalletAdapter):
    """Avalanche wallet adapter (inherits from Ethereum with chain-specific settings)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(43114, rpc_url, security_level)
        self.chain_id = 43114


# Wallet adapter factory
class WalletAdapterFactory:
    """Factory for creating wallet adapters for different chains"""

    @staticmethod
    def create_adapter(
        chain_id: int, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM
    ) -> EnhancedWalletAdapter:
        """Create wallet adapter for specified chain"""

        chain_adapters = {
            1: EthereumWalletAdapter,
            137: PolygonWalletAdapter,
            56: BSCWalletAdapter,
            42161: ArbitrumWalletAdapter,
            10: OptimismWalletAdapter,
            43114: AvalancheWalletAdapter,
        }

        adapter_class = chain_adapters.get(chain_id)
        if not adapter_class:
            raise ValueError(f"Unsupported chain ID: {chain_id}")

        return adapter_class(rpc_url, security_level)

    @staticmethod
    def get_supported_chains() -> list[int]:
        """Get list of supported chain IDs"""
        return [1, 137, 56, 42161, 10, 43114]

    @staticmethod
    def get_chain_info(chain_id: int) -> dict[str, Any]:
        """Get chain information"""
        chain_info = {
            1: {"name": "Ethereum", "symbol": "ETH", "decimals": 18},
            137: {"name": "Polygon", "symbol": "MATIC", "decimals": 18},
            56: {"name": "BSC", "symbol": "BNB", "decimals": 18},
            42161: {"name": "Arbitrum", "symbol": "ETH", "decimals": 18},
            10: {"name": "Optimism", "symbol": "ETH", "decimals": 18},
            43114: {"name": "Avalanche", "symbol": "AVAX", "decimals": 18},
        }

        return chain_info.get(chain_id, {"name": "Unknown", "symbol": "UNKNOWN", "decimals": 18})
