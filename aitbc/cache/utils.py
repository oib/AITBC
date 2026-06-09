"""
Cache utilities for key generation and serialization helpers.
"""

import hashlib
import json
from typing import Any


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate a consistent cache key from arguments.
    
    Args:
        prefix: Key prefix
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Cache key string
    """
    # Create a string representation of arguments
    key_parts = [prefix]
    
    if args:
        key_parts.extend(str(arg) for arg in args)
    
    if kwargs:
        # Sort kwargs for consistency
        for k in sorted(kwargs.keys()):
            key_parts.append(f"{k}={kwargs[k]}")
    
    key_string = ":".join(key_parts)
    
    # Hash if key is too long
    if len(key_string) > 200:
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"{prefix}:{key_hash}"
    
    return key_string


def serialize_value(value: Any) -> str:
    """
    Serialize value for storage in cache.
    
    Args:
        value: Value to serialize
        
    Returns:
        Serialized string
    """
    if isinstance(value, str):
        return value
    return json.dumps(value)


def deserialize_value(value: str) -> Any:
    """
    Deserialize value from cache.
    
    Args:
        value: Serialized string
        
    Returns:
        Deserialized value
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
