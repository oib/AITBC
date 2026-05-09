"""
Common error handling utilities for AITBC CLI
Provides standardized error handling patterns and utilities for CLI commands
"""

import sys
from typing import Optional, Callable, Any
from functools import wraps
from . import error, warning, info


class CLIError(Exception):
    """Base exception for CLI errors"""
    def __init__(self, message: str, exit_code: int = 1):
        self.message = message
        self.exit_code = exit_code
        super().__init__(self.message)


class NetworkError(CLIError):
    """Network-related errors"""
    def __init__(self, message: str):
        super().__init__(f"Network error: {message}", exit_code=2)


class ConfigurationError(CLIError):
    """Configuration-related errors"""
    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}", exit_code=3)


class ValidationError(CLIError):
    """Validation errors for user input"""
    def __init__(self, message: str):
        super().__init__(f"Validation error: {message}", exit_code=4)


class APIError(CLIError):
    """API-related errors"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        msg = f"API error: {message}"
        if status_code:
            msg += f" (HTTP {status_code})"
        super().__init__(msg, exit_code=5)


def handle_cli_error(func: Callable) -> Callable:
    """
    Decorator to standardize error handling in CLI commands.
    
    Catches common exceptions and displays user-friendly error messages.
    
    Args:
        func: Function to wrap with error handling
        
    Returns:
        Wrapped function with standardized error handling
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CLIError as e:
            error(e.message)
            sys.exit(e.exit_code)
        except KeyboardInterrupt:
            warning("\nOperation cancelled by user")
            sys.exit(130)
        except Exception as e:
            error(f"Unexpected error: {e}")
            sys.exit(1)
    return wrapper


def handle_async_cli_error(func: Callable) -> Callable:
    """
    Decorator to standardize error handling in async CLI commands.
    
    Args:
        func: Async function to wrap with error handling
        
    Returns:
        Wrapped async function with standardized error handling
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except CLIError as e:
            error(e.message)
            sys.exit(e.exit_code)
        except KeyboardInterrupt:
            warning("\nOperation cancelled by user")
            sys.exit(130)
        except Exception as e:
            error(f"Unexpected error: {e}")
            sys.exit(1)
    return wrapper


def safe_execute(
    operation: Callable,
    error_message: str = "Operation failed",
    default_return: Any = None,
    raise_on_error: bool = False
) -> Any:
    """
    Safely execute an operation with standardized error handling.
    
    Args:
        operation: Function to execute
        error_message: Custom error message prefix
        default_return: Value to return on error (if not raising)
        raise_on_error: Whether to raise exception on error
        
    Returns:
        Operation result or default_return on error
        
    Raises:
        Exception: If raise_on_error is True and operation fails
    """
    try:
        return operation()
    except Exception as e:
        if raise_on_error:
            raise
        error(f"{error_message}: {e}")
        return default_return


def validate_required_fields(data: dict, required_fields: list) -> None:
    """
    Validate that required fields are present in data dictionary.
    
    Args:
        data: Dictionary to validate
        required_fields: List of required field names
        
    Raises:
        ValidationError: If any required field is missing
    """
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    if missing_fields:
        raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")


def validate_url(url: str) -> bool:
    """
    Validate URL format.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if valid, False otherwise
    """
    import re
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(url_pattern.match(url))


def validate_address(address: str) -> bool:
    """
    Validate Ethereum address format.
    
    Args:
        address: Ethereum address string
        
    Returns:
        True if valid, False otherwise
    """
    import re
    # Basic Ethereum address validation (0x followed by 40 hex characters)
    address_pattern = re.compile(r'^0x[a-fA-F0-9]{40}$')
    return bool(address_pattern.match(address))
