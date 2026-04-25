"""
Base interfaces for cross-chain settlement bridges
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class BridgeStatus(Enum):
    """Bridge operation status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class BridgeConfig:
    """Bridge configuration"""

    name: str
    enabled: bool
    endpoint_address: str
    supported_chains: list[int]
    default_fee: str
    max_message_size: int
    timeout: int = 3600


@dataclass
class SettlementMessage:
    """Message to be settled across chains"""

    source_chain_id: int
    target_chain_id: int
    job_id: str
    receipt_hash: str
    proof_data: dict[str, Any]
    payment_amount: int
    payment_token: str
    nonce: int
    signature: str
    gas_limit: int | None = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class SettlementResult:
    """Result of settlement operation"""

    message_id: str
    status: BridgeStatus
    transaction_hash: str | None = None
    error_message: str | None = None
    gas_used: int | None = None
    fee_paid: int | None = None
    created_at: datetime = None
    completed_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class BridgeAdapter(ABC):
    """Abstract interface for bridge adapters"""

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.name = config.name

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the bridge adapter"""
        pass

    @abstractmethod
    async def send_message(self, message: SettlementMessage) -> SettlementResult:
        """Send message to target chain"""
        pass

    @abstractmethod
    async def verify_delivery(self, message_id: str) -> bool:
        """Verify message was delivered"""
        pass

    @abstractmethod
    async def get_message_status(self, message_id: str) -> SettlementResult:
        """Get current status of message"""
        pass

    @abstractmethod
    async def estimate_cost(self, message: SettlementMessage) -> dict[str, int]:
        """Estimate bridge fees"""
        pass

    @abstractmethod
    async def refund_failed_message(self, message_id: str) -> SettlementResult:
        """Refund failed message if supported"""
        pass

    def get_supported_chains(self) -> list[int]:
        """Get list of supported target chains"""
        return self.config.supported_chains

    def get_max_message_size(self) -> int:
        """Get maximum message size in bytes"""
        return self.config.max_message_size

    async def validate_message(self, message: SettlementMessage) -> bool:
        """Validate message before sending"""
        # Check if target chain is supported
        if message.target_chain_id not in self.get_supported_chains():
            raise ValueError(f"Chain {message.target_chain_id} not supported")

        # Check message size
        message_size = len(json.dumps(message.proof_data).encode())
        if message_size > self.get_max_message_size():
            raise ValueError(f"Message too large: {message_size} > {self.get_max_message_size()}")

        # Validate signature
        if not await self._verify_signature(message):
            raise ValueError("Invalid signature")

        return True

    async def _verify_signature(self, message: SettlementMessage) -> bool:
        """Verify message signature - to be implemented by subclass"""
        # This would verify the cryptographic signature
        # Implementation depends on the signature scheme used
        return True

    def _encode_payload(self, message: SettlementMessage) -> bytes:
        """Encode message payload - to be implemented by subclass"""
        # Each bridge may have different encoding requirements
        raise NotImplementedError("Subclass must implement _encode_payload")

    async def _get_gas_estimate(self, message: SettlementMessage) -> int:
        """Get gas estimate for message - to be implemented by subclass"""
        # Each bridge has different gas requirements
        raise NotImplementedError("Subclass must implement _get_gas_estimate")


class BridgeError(Exception):
    """Base exception for bridge errors"""

    pass


class BridgeNotSupportedError(BridgeError):
    """Raised when operation is not supported by bridge"""

    pass


class BridgeTimeoutError(BridgeError):
    """Raised when bridge operation times out"""

    pass


class BridgeInsufficientFundsError(BridgeError):
    """Raised when insufficient funds for bridge operation"""

    pass


class BridgeMessageTooLargeError(BridgeError):
    """Raised when message exceeds bridge limits"""

    pass


class EthereumBridge(BridgeAdapter):
    """Ethereum settlement bridge implementation"""
    
    def __init__(self, config: BridgeConfig, rpc_url: str = "http://localhost:8545"):
        super().__init__(config)
        self.rpc_url = rpc_url
        self._web3_client = None
        self._chain_id = 1  # Ethereum mainnet chain ID
    
    async def initialize(self) -> None:
        """Initialize Ethereum bridge with Web3 client"""
        try:
            from aitbc import Web3Client
            self._web3_client = Web3Client(self.rpc_url)
            # Test connection
            self._web3_client.get_eth_balance("0x0000000000000000000000000000000000000000")
        except Exception as e:
            raise BridgeError(f"Failed to initialize Ethereum bridge: {e}")
    
    async def send_message(self, message: SettlementMessage) -> SettlementResult:
        """Send message to Ethereum chain"""
        try:
            # Validate message
            await self.validate_message(message)
            
            # Encode payload for Ethereum
            payload = self._encode_payload(message)
            
            # Get gas estimate
            gas_estimate = await self._get_gas_estimate(message)
            
            # In production, would send transaction to Ethereum bridge contract
            # For now, return mock result
            result = SettlementResult(
                message_id=f"{message.job_id}_{message.nonce}",
                status=BridgeStatus.COMPLETED,
                transaction_hash="0x" + "0" * 64,  # Mock hash
                gas_used=gas_estimate,
                fee_paid=int(self.config.default_fee),
                completed_at=datetime.utcnow()
            )
            
            return result
            
        except Exception as e:
            return SettlementResult(
                message_id=f"{message.job_id}_{message.nonce}",
                status=BridgeStatus.FAILED,
                error_message=str(e)
            )
    
    async def verify_delivery(self, message_id: str) -> bool:
        """Verify message was delivered on Ethereum"""
        # In production, would query bridge contract
        # For now, return True
        return True
    
    async def get_message_status(self, message_id: str) -> SettlementResult:
        """Get current status of message"""
        # In production, would query bridge contract
        # For now, return mock completed status
        return SettlementResult(
                message_id=message_id,
                status=BridgeStatus.COMPLETED,
                transaction_hash="0x" + "0" * 64
            )
    
    async def estimate_cost(self, message: SettlementMessage) -> dict[str, int]:
        """Estimate bridge fees for Ethereum"""
        gas_estimate = await self._get_gas_estimate(message)
        gas_price = self._web3_client.get_gas_price() if self._web3_client else 20000000000  # 20 Gwei
        
        return {
            "gas_estimate": gas_estimate,
            "gas_price": gas_price,
            "total_fee": gas_estimate * gas_price,
            "bridge_fee": int(self.config.default_fee)
        }
    
    async def refund_failed_message(self, message_id: str) -> SettlementResult:
        """Refund failed message on Ethereum"""
        # In production, would execute refund transaction
        # For now, return mock result
        return SettlementResult(
            message_id=message_id,
            status=BridgeStatus.REFUNDED,
            transaction_hash="0x" + "0" * 64
        )
    
    def _encode_payload(self, message: SettlementMessage) -> bytes:
        """Encode message payload for Ethereum using RLP encoding"""
        try:
            # Ethereum transaction fields for bridge
            tx_dict = {
                'nonce': message.nonce,
                'gasPrice': 20000000000,  # 20 Gwei in wei
                'gas': message.gas_limit or 100000,
                'to': self.config.endpoint_address,
                'value': message.payment_amount,
                'data': self._encode_proof_data(message.proof_data),
                'chainId': self._chain_id
            }
            
            # RLP encode the transaction
            # In production, use actual RLP encoding library
            # For now, return JSON-encoded bytes
            import json
            return json.dumps(tx_dict).encode('utf-8')
            
        except Exception as e:
            raise BridgeError(f"Failed to encode Ethereum payload: {e}")
    
    def _encode_proof_data(self, proof_data: dict[str, Any]) -> str:
        """Encode proof data for Ethereum transaction data field"""
        import json
        return json.dumps(proof_data)
    
    async def _get_gas_estimate(self, message: SettlementMessage) -> int:
        """Get gas estimate for Ethereum transaction"""
        try:
            if self._web3_client:
                # Use Web3 to estimate gas
                gas_estimate = self._web3_client.estimate_gas({
                    'to': self.config.endpoint_address,
                    'value': message.payment_amount,
                    'data': self._encode_proof_data(message.proof_data)
                })
                # Add safety buffer (1.2x)
                return int(gas_estimate * 1.2)
            else:
                # Default gas estimate for bridge transaction
                return 100000  # 100k gas units
                
        except Exception as e:
            # Fallback to default estimate
            return 100000
