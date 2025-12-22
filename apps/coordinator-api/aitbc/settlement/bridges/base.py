"""
Base interfaces for cross-chain settlement bridges
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime


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
    supported_chains: List[int]
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
    proof_data: Dict[str, Any]
    payment_amount: int
    payment_token: str
    nonce: int
    signature: str
    gas_limit: Optional[int] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class SettlementResult:
    """Result of settlement operation"""
    message_id: str
    status: BridgeStatus
    transaction_hash: Optional[str] = None
    error_message: Optional[str] = None
    gas_used: Optional[int] = None
    fee_paid: Optional[int] = None
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    
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
    async def estimate_cost(self, message: SettlementMessage) -> Dict[str, int]:
        """Estimate bridge fees"""
        pass
    
    @abstractmethod
    async def refund_failed_message(self, message_id: str) -> SettlementResult:
        """Refund failed message if supported"""
        pass
    
    def get_supported_chains(self) -> List[int]:
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
