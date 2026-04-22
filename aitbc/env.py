"""
AITBC Environment Variable Helpers
Centralized utilities for loading and managing environment variables
"""

import os
from typing import Optional
from .exceptions import ConfigurationError


def get_env_var(key: str, default: str = "") -> str:
    """
    Get an environment variable with a default value.
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        Environment variable value or default
    """
    return os.getenv(key, default)


def get_required_env_var(key: str) -> str:
    """
    Get a required environment variable, raise error if not set.
    
    Args:
        key: Environment variable name
        
    Returns:
        Environment variable value
        
    Raises:
        ConfigurationError: If environment variable is not set
    """
    value = os.getenv(key)
    if value is None:
        raise ConfigurationError(f"Required environment variable '{key}' is not set")
    return value


def get_bool_env_var(key: str, default: bool = False) -> bool:
    """
    Get a boolean environment variable.
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        True if variable is set to 'true', '1', 'yes', or 'on' (case-insensitive)
        False if variable is set to 'false', '0', 'no', or 'off' (case-insensitive)
        Default value if not set
    """
    value = os.getenv(key, "").lower()
    if not value:
        return default
    return value in ("true", "1", "yes", "on")


def get_int_env_var(key: str, default: int = 0) -> int:
    """
    Get an integer environment variable.
    
    Args:
        key: Environment variable name
        default: Default value if not set or invalid
        
    Returns:
        Integer value or default
    """
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def get_float_env_var(key: str, default: float = 0.0) -> float:
    """
    Get a float environment variable.
    
    Args:
        key: Environment variable name
        default: Default value if not set or invalid
        
    Returns:
        Float value or default
    """
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def get_list_env_var(key: str, separator: str = ",", default: Optional[list] = None) -> list:
    """
    Get a list environment variable.
    
    Args:
        key: Environment variable name
        separator: Separator for list items
        default: Default value if not set
        
    Returns:
        List of values or default
    """
    if default is None:
        default = []
    value = os.getenv(key, "")
    if not value:
        return default
    return [item.strip() for item in value.split(separator) if item.strip()]
