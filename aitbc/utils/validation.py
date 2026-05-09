"""
AITBC Validation Utilities
Common validators for AITBC applications
"""

import re
from typing import Any, Optional
from .exceptions import ValidationError


def validate_address(address: str) -> bool:
    """
    Validate an AITBC blockchain address.
    
    Args:
        address: Address string to validate
        
    Returns:
        True if address is valid format
        
    Raises:
        ValidationError: If address format is invalid
    """
    if not address:
        raise ValidationError("Address cannot be empty")
    
    # AITBC addresses typically start with 'ait' and are alphanumeric (variable length)
    pattern = r'^ait[a-z0-9]+$'
    if not re.match(pattern, address):
        raise ValidationError(f"Invalid address format: {address}")
    
    return True


def validate_hash(hash_str: str) -> bool:
    """
    Validate a hash string (hex string of expected length).
    
    Args:
        hash_str: Hash string to validate
        
    Returns:
        True if hash is valid format
        
    Raises:
        ValidationError: If hash format is invalid
    """
    if not hash_str:
        raise ValidationError("Hash cannot be empty")
    
    # Hashes are typically 64-character hex strings
    pattern = r'^[a-f0-9]{64}$'
    if not re.match(pattern, hash_str):
        raise ValidationError(f"Invalid hash format: {hash_str}")
    
    return True


def validate_url(url: str) -> bool:
    """
    Validate a URL string.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if URL is valid format
        
    Raises:
        ValidationError: If URL format is invalid
    """
    if not url:
        raise ValidationError("URL cannot be empty")
    
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    if not re.match(pattern, url):
        raise ValidationError(f"Invalid URL format: {url}")
    
    return True


def validate_port(port: int) -> bool:
    """
    Validate a port number.
    
    Args:
        port: Port number to validate
        
    Returns:
        True if port is valid
        
    Raises:
        ValidationError: If port is invalid
    """
    if not isinstance(port, int):
        raise ValidationError(f"Port must be an integer, got {type(port)}")
    
    if port < 1 or port > 65535:
        raise ValidationError(f"Port must be between 1 and 65535, got {port}")
    
    return True


def validate_email(email: str) -> bool:
    """
    Validate an email address.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email is valid format
        
    Raises:
        ValidationError: If email format is invalid
    """
    if not email:
        raise ValidationError("Email cannot be empty")
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError(f"Invalid email format: {email}")
    
    return True


def validate_non_empty(value: Any, field_name: str = "value") -> bool:
    """
    Validate that a value is not empty.
    
    Args:
        value: Value to validate
        field_name: Name of the field for error message
        
    Returns:
        True if value is not empty
        
    Raises:
        ValidationError: If value is empty
    """
    if value is None:
        raise ValidationError(f"{field_name} cannot be None")
    
    if isinstance(value, str) and not value.strip():
        raise ValidationError(f"{field_name} cannot be empty string")
    
    if isinstance(value, (list, dict)) and len(value) == 0:
        raise ValidationError(f"{field_name} cannot be empty")
    
    return True


def validate_positive_number(value: Any, field_name: str = "value") -> bool:
    """
    Validate that a value is a positive number.
    
    Args:
        value: Value to validate
        field_name: Name of the field for error message
        
    Returns:
        True if value is positive
        
    Raises:
        ValidationError: If value is not positive
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be a number, got {type(value)}")
    
    if value <= 0:
        raise ValidationError(f"{field_name} must be positive, got {value}")
    
    return True


def validate_range(value: Any, min_val: float, max_val: float, field_name: str = "value") -> bool:
    """
    Validate that a value is within a specified range.
    
    Args:
        value: Value to validate
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        field_name: Name of the field for error message
        
    Returns:
        True if value is within range
        
    Raises:
        ValidationError: If value is outside range
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be a number, got {type(value)}")
    
    if value < min_val or value > max_val:
        raise ValidationError(f"{field_name} must be between {min_val} and {max_val}, got {value}")
    
    return True


def validate_chain_id(chain_id: str) -> bool:
    """
    Validate a chain ID.
    
    Args:
        chain_id: Chain ID to validate
        
    Returns:
        True if chain ID is valid
        
    Raises:
        ValidationError: If chain ID is invalid
    """
    if not chain_id:
        raise ValidationError("Chain ID cannot be empty")
    
    # Chain IDs are typically alphanumeric with hyphens
    pattern = r'^[a-z0-9\-]+$'
    if not re.match(pattern, chain_id):
        raise ValidationError(f"Invalid chain ID format: {chain_id}")
    
    return True


def validate_uuid(uuid_str: str) -> bool:
    """
    Validate a UUID string.
    
    Args:
        uuid_str: UUID string to validate
        
    Returns:
        True if UUID is valid format
        
    Raises:
        ValidationError: If UUID format is invalid
    """
    if not uuid_str:
        raise ValidationError("UUID cannot be empty")
    
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if not re.match(pattern, uuid_str.lower()):
        raise ValidationError(f"Invalid UUID format: {uuid_str}")
    
    return True
