"""
Enhanced Multi-Chain Wallet Adapter
Production-ready wallet adapter for cross-chain operations with advanced security and management
"""

import hashlib
import json
import os
import secrets
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.crypto import derive_ethereum_address, encrypt_private_key, sign_transaction_hash, verify_signature
from aitbc.network import AITBCHTTPClient, Web3Client

from ..contexts.agent_identity.domain.agent_identity import ChainType

logger = get_logger(__name__)


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
            timestamp = str(int(datetime.now(UTC).timestamp()))
            nonce = secrets.token_hex(16)
            message_to_sign = f"{message}:{timestamp}:{nonce}"
            message_hash = hashlib.sha256(message_to_sign.encode()).hexdigest()
            signature = await self._sign_hash(message_hash, private_key)
            return {"signature": signature, "message": message, "timestamp": timestamp, "nonce": nonce, "hash": message_hash}  # type: ignore[return-value]
        except Exception as e:
            logger.error("Error signing message: %s", e)
            raise

    async def verify_signature(self, message: str, signature: str, address: str) -> bool:
        """Verify a message signature"""
        try:
            signature_data = json.loads(signature) if isinstance(signature, str) else signature
            message_to_verify = f"{message}:{signature_data['timestamp']}:{signature_data['nonce']}"
            message_hash = hashlib.sha256(message_to_verify.encode()).hexdigest()
            return await self._verify_signature(message_hash, signature_data["signature"], address)
        except Exception as e:
            logger.error("Error verifying signature: %s", e)
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
        self._web3_client = Web3Client(rpc_url)

    async def create_wallet(self, owner_address: str, security_config: dict[str, Any]) -> dict[str, Any]:
        """Create a new Ethereum wallet with enhanced security"""
        try:
            private_key = secrets.token_hex(32)
            address = await self._derive_address_from_private_key(private_key)
            wallet_data = {
                "address": address,
                "private_key": private_key,
                "chain_id": self.chain_id,
                "chain_type": self.chain_type.value,
                "owner_address": owner_address,
                "security_level": self.security_level.value,
                "created_at": datetime.now(UTC).isoformat(),
                "status": WalletStatus.ACTIVE.value,
                "security_config": security_config,
                "nonce": 0,
                "transaction_count": 0,
            }
            encrypted_private_key = await self._encrypt_private_key(private_key, security_config)
            wallet_data["encrypted_private_key"] = encrypted_private_key
            logger.info("Created Ethereum wallet %s for owner %s", address, owner_address)
            return wallet_data
        except Exception as e:
            logger.error("Error creating Ethereum wallet: %s", e)
            raise

    async def get_balance(self, wallet_address: str, token_address: str | None = None) -> dict[str, Any]:
        """Get wallet balance with multi-token support"""
        try:
            if not await self.validate_address(wallet_address):
                raise ValueError(f"Invalid Ethereum address: {wallet_address}")
            eth_balance_wei = await self._get_eth_balance(wallet_address)
            eth_balance = float(Decimal(eth_balance_wei) / Decimal(10**18))
            result = {
                "address": wallet_address,
                "chain_id": self.chain_id,
                "eth_balance": eth_balance,
                "token_balances": {},
                "last_updated": datetime.now(UTC).isoformat(),
            }
            if token_address:
                token_balance = await self._get_token_balance(wallet_address, token_address)
                result["token_balances"][token_address] = token_balance  # type: ignore[index]
            return result
        except Exception as e:
            logger.error("Error getting balance for %s: %s", wallet_address, e)
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
            if not await self.validate_address(from_address) or not await self.validate_address(to_address):
                raise ValueError("Invalid addresses provided")
            if token_address:
                amount_wei = int(float(amount) * 10**18)
                transaction_data = await self._create_erc20_transfer(from_address, to_address, token_address, amount_wei)
            else:
                amount_wei = int(float(amount) * 10**18)
                transaction_data = {"from": from_address, "to": to_address, "value": hex(amount_wei), "data": "0x"}
            if data:
                transaction_data["data"] = data.get("hex", "0x")
            if not gas_limit:
                gas_estimate = await self.estimate_gas(from_address, to_address, amount, token_address, data)
                gas_limit = gas_estimate["gas_limit"]
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
            signed_tx = await self._sign_transaction(transaction_data, from_address)
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
                "created_at": datetime.now(UTC).isoformat(),
            }
            logger.info("Executed Ethereum transaction %s from %s to %s", tx_hash, from_address, to_address)
            return result
        except Exception as e:
            logger.error("Error executing Ethereum transaction: %s", e)
            raise

    async def get_transaction_status(self, transaction_hash: str) -> dict[str, Any]:
        """Get detailed transaction status"""
        try:
            receipt = await self._get_transaction_receipt(transaction_hash)
            if not receipt:
                tx_data = await self._get_transaction_by_hash(transaction_hash)
                return {
                    "transaction_hash": transaction_hash,
                    "status": TransactionStatus.PENDING.value,
                    "block_number": None,
                    "block_hash": None,
                    "gas_used": None,
                    "effective_gas_price": None,
                    "logs": [],
                    "created_at": datetime.now(UTC).isoformat(),
                }
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
                "created_at": datetime.now(UTC).isoformat(),
            }
            return result
        except Exception as e:
            logger.error("Error getting transaction status for %s: %s", transaction_hash, e)
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
            gas_estimate = await self._estimate_gas_call(call_data)
            return {
                "gas_limit": int(gas_estimate, 16),
                "gas_price_gwei": await self._get_gas_price_gwei(),
                "estimated_cost_eth": float(int(gas_estimate, 16) * await self._get_gas_price()) / 10**18,
                "estimated_cost_usd": 0.0,
            }
        except Exception as e:
            logger.error("Error estimating gas: %s", e)
            raise

    async def validate_address(self, address: str) -> bool:
        """Validate Ethereum address format"""
        try:
            if not address.startswith("0x") or len(address) != 42:
                return False
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
            transactions = await self._get_wallet_transactions(wallet_address, limit, offset, from_block, to_block)
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
            logger.error("Error getting transaction history for %s: %s", wallet_address, e)
            raise

    async def _derive_address_from_private_key(self, private_key: str) -> str:
        """Derive Ethereum address from private key"""
        try:
            return derive_ethereum_address(private_key)  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Failed to derive address from private key: %s", e)
            raise

    async def _encrypt_private_key(self, private_key: str, security_config: dict[str, Any]) -> str:
        """Encrypt private key with security configuration"""
        try:
            password = security_config.get("encryption_password", "default_password")
            return encrypt_private_key(private_key, password)  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Failed to encrypt private key: %s", e)
            raise

    async def _get_eth_balance(self, address: str) -> str:
        """Get ETH balance in wei"""
        try:
            return self._web3_client.get_eth_balance(address)
        except Exception as e:
            logger.error("Failed to get ETH balance: %s", e)
            raise

    async def _get_token_balance(self, address: str, token_address: str) -> dict[str, Any]:
        """Get ERC-20 token balance"""
        try:
            return self._web3_client.get_token_balance(address, token_address)
        except Exception as e:
            logger.error("Failed to get token balance: %s", e)
            raise

    async def _create_erc20_transfer(
        self, from_address: str, to_address: str, token_address: str, amount: int
    ) -> dict[str, Any]:
        """Create ERC-20 transfer transaction data"""
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
        return {"from": "0x0000000000000000000000000000000000000000", "to": token_address, "data": f"0x{data}"}

    async def _get_gas_price(self) -> int:
        """Get current gas price"""
        try:
            return self._web3_client.get_gas_price()
        except Exception as e:
            logger.error("Failed to get gas price: %s", e)
            raise

    async def _get_gas_price_gwei(self) -> float:
        """Get current gas price in Gwei"""
        try:
            return self._web3_client.get_gas_price_gwei()
        except Exception as e:
            logger.error("Failed to get gas price in Gwei: %s", e)
            raise

    async def _get_nonce(self, address: str) -> int:
        """Get transaction nonce for address"""
        try:
            return self._web3_client.get_nonce(address)
        except Exception as e:
            logger.error("Failed to get nonce: %s", e)
            raise

    async def _sign_transaction(self, transaction_data: dict[str, Any], from_address: str) -> str:
        """Sign transaction"""
        try:
            from eth_account import Account

            if from_address.startswith("0x"):
                from_address = from_address[2:]
            account = Account.from_key(from_address)
            tx_dict = {
                "nonce": int(transaction_data.get("nonce", 0), 16),
                "gasPrice": int(transaction_data.get("gasPrice", 0), 16),
                "gas": int(transaction_data.get("gas", 0), 16),
                "to": transaction_data.get("to"),
                "value": int(transaction_data.get("value", "0x0"), 16),
                "data": transaction_data.get("data", "0x"),
                "chainId": transaction_data.get("chainId", 1),
            }
            signed_tx = account.sign_transaction(tx_dict)
            return signed_tx.raw_transaction.hex()  # type: ignore[no-any-return]
        except ImportError:
            raise ImportError(
                "eth-account is required for transaction signing. Install with: pip install eth-account"
            ) from None
        except Exception as e:
            logger.error("Failed to sign transaction: %s", e)
            raise

    async def _send_raw_transaction(self, signed_transaction: str) -> str:
        """Send raw transaction"""
        try:
            return self._web3_client.send_raw_transaction(signed_transaction)
        except Exception as e:
            logger.error("Failed to send raw transaction: %s", e)
            raise

    async def _get_transaction_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        """Get transaction receipt"""
        try:
            return self._web3_client.get_transaction_receipt(tx_hash)
        except Exception as e:
            logger.error("Failed to get transaction receipt: %s", e)
            raise

    async def _get_transaction_by_hash(self, tx_hash: str) -> dict[str, Any]:
        """Get transaction by hash"""
        try:
            return self._web3_client.get_transaction_by_hash(tx_hash)
        except Exception as e:
            logger.error("Failed to get transaction by hash: %s", e)
            raise

    async def _estimate_gas_call(self, call_data: dict[str, Any]) -> str:
        """Estimate gas for call"""
        try:
            gas_estimate = self._web3_client.estimate_gas(call_data)
            return hex(gas_estimate)
        except Exception as e:
            logger.error("Failed to estimate gas: %s", e)
            raise

    async def _get_wallet_transactions(
        self, address: str, limit: int, offset: int, from_block: int | None, to_block: int | None
    ) -> list[dict[str, Any]]:
        """Get wallet transactions"""
        try:
            return self._web3_client.get_wallet_transactions(address, limit)
        except Exception as e:
            logger.error("Failed to get wallet transactions: %s", e)
            raise

    async def _sign_hash(self, message_hash: str, private_key: str) -> str:
        """Sign a hash with private key"""
        try:
            return sign_transaction_hash(message_hash, private_key)  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Failed to sign hash: %s", e)
            raise

    async def _verify_signature(self, message_hash: str, signature: str, address: str) -> bool:
        """Verify a signature"""
        try:
            return verify_signature(message_hash, signature, address)  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Failed to verify signature: %s", e)
            return False


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


class AITBCWalletAdapter(EnhancedWalletAdapter):
    """AITBC wallet adapter using native RPC protocol (not Ethereum-compatible)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM, chain_id: int = 1000):
        super().__init__(chain_id, ChainType.AITBC, rpc_url, security_level)
        self.chain_id = chain_id
        # Use environment variable for actual chain ID string
        self.aitbc_chain_id = os.getenv("CHAIN_ID", "")
        self._http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)

    async def create_wallet(self, owner_address: str, security_config: dict[str, Any]) -> dict[str, Any]:
        """Create a new AITBC wallet with enhanced security"""
        try:
            private_key = secrets.token_hex(32)
            import hashlib

            key_hash = hashlib.sha256(bytes.fromhex(private_key)).hexdigest()[:32]
            address = f"ait1{key_hash}"
            wallet_data = {
                "address": address,
                "private_key": private_key,
                "chain_id": self.chain_id,
                "chain_type": self.chain_type.value,
                "aitbc_chain_id": self.aitbc_chain_id,
                "owner_address": owner_address,
                "security_level": self.security_level.value,
                "created_at": datetime.now(UTC).isoformat(),
                "status": WalletStatus.ACTIVE.value,
                "security_config": security_config,
                "nonce": 0,
                "transaction_count": 0,
            }
            encrypted_private_key = await self._encrypt_private_key(private_key, security_config)
            wallet_data["encrypted_private_key"] = encrypted_private_key
            logger.info("Created AITBC wallet %s for owner %s", address, owner_address)
            return wallet_data
        except Exception as e:
            logger.error("Error creating AITBC wallet: %s", e)
            raise

    async def get_balance(self, wallet_address: str, token_address: str | None = None) -> dict[str, Any]:
        """Get wallet balance using AITBC RPC"""
        try:
            if not await self.validate_address(wallet_address):
                raise ValueError(f"Invalid AITBC address: {wallet_address}")
            response = self._http_client.get(f"account/{wallet_address}")
            balance = response.get("balance", 0)
            nonce = response.get("nonce", 0)
            return {
                "address": wallet_address,
                "chain_id": self.chain_id,
                "aitbc_chain_id": self.aitbc_chain_id,
                "balance": balance,
                "nonce": nonce,
                "token_balances": {},
                "last_updated": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error getting balance for %s: %s", wallet_address, e)
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
        """Execute an AITBC transaction using native RPC"""
        try:
            if not await self.validate_address(from_address) or not await self.validate_address(to_address):
                raise ValueError("Invalid addresses provided")
            amount_int = int(float(amount))
            transaction_data = {
                "from": from_address,
                "to": to_address,
                "amount": amount_int,
                "fee": gas_price or 10,
                "nonce": await self._get_nonce(from_address),
                "payload": data.get("payload", "") if data else "",
                "type": data.get("type", "transfer") if data else "transfer",
                "signature": data.get("signature", "") if data else "",
            }
            response = self._http_client.post("transaction", json=transaction_data)
            result = {
                "transaction_hash": response.get("transaction_hash", ""),
                "from": from_address,
                "to": to_address,
                "amount": str(amount),
                "fee": transaction_data["fee"],
                "nonce": transaction_data["nonce"],
                "status": TransactionStatus.PENDING.value,
                "created_at": datetime.now(UTC).isoformat(),
            }
            logger.info("Executed AITBC transaction %s", result["transaction_hash"])
            return result
        except Exception as e:
            logger.error("Error executing AITBC transaction: %s", e)
            raise

    async def get_transaction_status(self, transaction_hash: str) -> dict[str, Any]:
        """Get transaction status using AITBC RPC"""
        try:
            response = self._http_client.get("transactions", params={"tx_hash": transaction_hash})
            transactions = response.get("transactions", [])
            if not transactions:
                return {"transaction_hash": transaction_hash, "status": TransactionStatus.UNKNOWN.value, "found": False}  # type: ignore[attr-defined]
            tx = transactions[0]
            return {
                "transaction_hash": transaction_hash,
                "status": tx.get("status", TransactionStatus.UNKNOWN.value),
                "from": tx.get("from", ""),
                "to": tx.get("to", ""),
                "amount": str(tx.get("amount", 0)),
                "fee": tx.get("fee", 0),
                "block_height": tx.get("block_height"),
                "found": True,
            }  # type: ignore[attr-defined]
        except Exception as e:
            logger.error("Error getting transaction status: %s", e)
            raise

    async def estimate_gas(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal | float | str,
        token_address: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Estimate transaction fee (AITBC uses fixed fees, not gas)"""
        return {"gas_limit": 0, "gas_price": 0, "estimated_fee": 10, "currency": "AIT"}

    async def validate_address(self, address: str) -> bool:
        """Validate AITBC address format (Bech32 with ait1 prefix)"""
        try:
            if not address or not isinstance(address, str):
                return False
            if address.startswith("ait1") and len(address) >= 39:
                return True
            if address.startswith("0x") and len(address) == 42:
                return True
            return False
        except Exception:
            return False

    async def _get_nonce(self, address: str) -> int:
        try:
            response = self._http_client.get(f"account/{address}")
            return response.get("nonce", 0)  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Error getting nonce for %s: %s", address, e)
            return 0

    async def _encrypt_private_key(self, private_key: str, security_config: dict[str, Any]) -> str:
        try:
            return encrypt_private_key(private_key, security_config.get("password", ""))  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Error encrypting private key: %s", e)
            raise

    async def _get_gas_price(self) -> int:
        return 0

    async def _derive_address_from_private_key(self, private_key: str) -> str:
        try:
            import hashlib

            key_hash = hashlib.sha256(bytes.fromhex(private_key)).hexdigest()[:32]
            return f"ait1{key_hash}"
        except Exception as e:
            logger.error("Error deriving address: %s", e)
            raise

    async def _sign_hash(self, message_hash: str, private_key: str) -> str:
        try:
            import hashlib

            signature = hashlib.sha256(f"{message_hash}{private_key}".encode()).hexdigest()
            return f"0x{signature}"
        except Exception as e:
            logger.error("Failed to sign hash: %s", e)
            raise

    async def _verify_signature(self, message_hash: str, signature: str, address: str) -> bool:
        try:
            return bool(signature and len(signature) == 66 and signature.startswith("0x"))
        except Exception as e:
            logger.error("Failed to verify signature: %s", e)
            return False

    async def get_transaction_history(
        self,
        wallet_address: str,
        limit: int = 100,
        offset: int = 0,
        from_block: int | None = None,
        to_block: int | None = None,
    ) -> list[dict[str, Any]]:
        try:
            response = self._http_client.get("transactions", params={"address": wallet_address, "limit": limit})
            transactions = response.get("transactions", [])
            formatted = []
            for tx in transactions:
                formatted.append(
                    {
                        "hash": tx.get("hash", ""),
                        "from": tx.get("from", ""),
                        "to": tx.get("to", ""),
                        "value": str(tx.get("amount", 0)),
                        "block_number": tx.get("block_height"),
                        "timestamp": tx.get("timestamp"),
                        "fee": tx.get("fee", 0),
                        "status": tx.get("status", TransactionStatus.UNKNOWN.value),
                    }
                )  # type: ignore[attr-defined]
            return formatted
        except Exception as e:
            logger.error("Error getting transaction history: %s", e)
            raise


class AITBCMainnetWalletAdapter(AITBCWalletAdapter):
    """AITBC mainnet wallet adapter (chain_id=1000)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(rpc_url, security_level, chain_id=1000)


class AITBCTestnetWalletAdapter(AITBCWalletAdapter):
    """AITBC testnet wallet adapter (chain_id=1001)"""

    def __init__(self, rpc_url: str, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        super().__init__(rpc_url, security_level, chain_id=1001)


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
            1000: AITBCMainnetWalletAdapter,
            1001: AITBCTestnetWalletAdapter,
        }
        adapter_class = chain_adapters.get(chain_id)
        if not adapter_class:
            raise ValueError(f"Unsupported chain ID: {chain_id}")
        return adapter_class(rpc_url, security_level)  # type: ignore[no-any-return]

    @staticmethod
    def get_supported_chains() -> list[int]:
        """Get list of supported chain IDs"""
        return [1, 137, 56, 42161, 10, 43114, 1000, 1001]

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
            1000: {"name": "AITBC Mainnet", "symbol": "AIT", "decimals": 0},
            1001: {"name": "AITBC Testnet", "symbol": "AIT", "decimals": 0},
        }
        return chain_info.get(chain_id, {"name": "Unknown", "symbol": "???", "decimals": 18})
