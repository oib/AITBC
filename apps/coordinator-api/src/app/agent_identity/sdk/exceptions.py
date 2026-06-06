"""
SDK Exceptions
Custom exceptions for the Agent Identity SDK
"""


class AgentIdentityError(Exception):
    """Base exception for agent identity operations"""

    pass


class VerificationError(AgentIdentityError):
    """Exception raised during identity verification"""

    pass


class WalletError(AgentIdentityError):
    """Exception raised during wallet operations"""

    pass


class NetworkError(AgentIdentityError):
    """Exception raised during network operations"""

    pass


class ValidationError(AgentIdentityError):
    """Exception raised during input validation"""

    pass


class AuthenticationError(AgentIdentityError):
    """Exception raised during authentication"""

    pass


class RateLimitError(AgentIdentityError):
    """Exception raised when rate limits are exceeded"""

    pass


class InsufficientFundsError(WalletError):
    """Exception raised when insufficient funds for transaction"""

    pass


class TransactionError(WalletError):
    """Exception raised during transaction execution"""

    pass


class ChainNotSupportedError(NetworkError):
    """Exception raised when chain is not supported"""

    pass


class IdentityNotFoundError(AgentIdentityError):
    """Exception raised when identity is not found"""

    pass


class MappingNotFoundError(AgentIdentityError):
    """Exception raised when cross-chain mapping is not found"""

    pass
