"""
Secure pickle utilities for safe deserialization
"""

import hashlib
import pickle
from typing import Any


def safe_loads(data: bytes, max_size: int = 10 * 1024 * 1024) -> Any:
    """
    Safely load pickled data with size限制 and validation
    
    Args:
        data: Pickled bytes to deserialize
        max_size: Maximum allowed size in bytes (default 10MB)
    
    Returns:
        Deserialized object
    
    Raises:
        ValueError: If data exceeds max_size or is invalid
        pickle.UnpicklingError: If deserialization fails
    """
    if len(data) > max_size:
        raise ValueError(f"Data size {len(data)} exceeds maximum allowed size {max_size}")

    try:
        return pickle.loads(data)
    except (pickle.UnpicklingError, EOFError) as e:
        raise ValueError(f"Failed to unpickle data: {e}")


def safe_dumps(obj: Any, protocol: int = pickle.HIGHEST_PROTOCOL) -> bytes:
    """
    Safely serialize object to pickle format
    
    Args:
        obj: Object to serialize
        protocol: Pickle protocol version
    
    Returns:
        Pickled bytes
    """
    return pickle.dumps(obj, protocol=protocol)


def compute_integrity_hash(data: bytes) -> str:
    """
    Compute SHA256 hash for data integrity verification
    
    Args:
        data: Bytes to hash
    
    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(data).hexdigest()
