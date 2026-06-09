"""
Cache utilities and helper functions for AITBC caching system.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CacheEntry:
    """Cache entry with value and expiration"""
    value: Any
    expires_at: datetime | None = None
    hit_count: int = 0
    created_at: datetime = None
    last_accessed: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_accessed is None:
            self.last_accessed = datetime.now()

    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def update_access(self):
        """Update last access time"""
        self.last_accessed = datetime.now()


def _generate_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """
    Generate a cache key from function name and arguments.
    
    Args:
        func_name: Name of the function
        args: Positional arguments
        kwargs: Keyword arguments
        
    Returns:
        Cache key string
    """
    # Create a string representation of arguments
    arg_str = ":".join(str(arg) for arg in args)
    kwarg_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    
    # Combine and hash if too long
    key = f"{func_name}:{arg_str}:{kwarg_str}"
    if len(key) > 200:
        return f"{func_name}:{hashlib.sha256(key.encode()).hexdigest()[:16]}"
    return key


def _generate_blockchain_cache_key(operation: str, args: tuple, kwargs: dict) -> str:
    """
    Generate a cache key for blockchain operations.
    
    Args:
        operation: Type of blockchain operation
        args: Positional arguments
        kwargs: Keyword arguments
        
    Returns:
        Cache key string
    """
    # Extract common blockchain parameters
    chain_id = kwargs.get("chain_id", args[0] if args else "default")
    
    # Create operation-specific key
    if operation == "account_balance":
        address = kwargs.get("address", args[1] if len(args) > 1 else "")
        return f"account_balance:{chain_id}:{address.lower()}"
    elif operation == "block":
        block_number = kwargs.get("block_number", args[1] if len(args) > 1 else "")
        return f"block:{chain_id}:{block_number}"
    elif operation == "transaction":
        tx_hash = kwargs.get("tx_hash", args[1] if len(args) > 1 else "")
        return f"transaction:{chain_id}:{tx_hash.lower()}"
    else:
        # Generic key generation
        return _generate_cache_key(f"blockchain_{operation}", args, kwargs)
