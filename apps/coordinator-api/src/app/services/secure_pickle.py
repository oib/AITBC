"""
Secure JSON serialization utilities for safe deserialization.
Replaces pickle with JSON to eliminate RCE vulnerability (CVE-2020-XXXX).
"""

import hashlib
import json
from typing import Any


def safe_loads(data: bytes, max_size: int = 10 * 1024 * 1024) -> Any:
    """
    Safely load JSON data with size validation.

    Args:
        data: JSON bytes to deserialize
        max_size: Maximum allowed size in bytes (default 10MB)

    Returns:
        Deserialized object

    Raises:
        ValueError: If data exceeds max_size or is invalid JSON
    """
    if len(data) > max_size:
        raise ValueError(f"Data size {len(data)} exceeds maximum allowed size {max_size}")

    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to deserialize JSON data: {e}")


def safe_dumps(obj: Any) -> bytes:
    """
    Safely serialize object to JSON bytes.

    Args:
        obj: Object to serialize (must be JSON-serializable)

    Returns:
        JSON-encoded bytes
    """
    return json.dumps(obj).encode("utf-8")


def compute_integrity_hash(data: bytes) -> str:
    """
    Compute SHA256 hash for data integrity verification

    Args:
        data: Bytes to hash

    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(data).hexdigest()
