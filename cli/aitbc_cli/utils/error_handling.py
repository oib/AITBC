"""
Common error handling utilities for AITBC CLI
Provides standardized error handling patterns and utilities for CLI commands
"""

import json as _json
import sys
from collections.abc import Callable
from functools import wraps
from typing import Any

import click

from . import error, warning

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class CLIError(Exception):
    """Base exception for CLI errors.

    ``message`` is the raw user-facing message (no prefix).
    ``exit_code`` is the process exit code to use.
    """

    def __init__(self, message: str, exit_code: int = 1):
        self.message = message
        self.exit_code = exit_code
        super().__init__(self.message)


class NetworkError(CLIError):
    """Network-related errors (exit 2)"""

    def __init__(self, message: str):
        super().__init__(message, exit_code=2)


class ConfigurationError(CLIError):
    """Configuration-related errors (exit 3)"""

    def __init__(self, message: str):
        super().__init__(message, exit_code=3)


class ValidationError(CLIError):
    """Validation errors for user input (exit 4)"""

    def __init__(self, message: str):
        super().__init__(message, exit_code=4)


class APIError(CLIError):
    """API-related errors (exit 5)"""

    def __init__(self, message: str, status_code: int | None = None):
        msg = message
        if status_code:
            msg += f" (HTTP {status_code})"
        super().__init__(msg, exit_code=5)


# ---------------------------------------------------------------------------
# Auto-categorisation
# ---------------------------------------------------------------------------

_NETWORK_KEYWORDS = ("network", "connect", "connection", "timeout", "unreachable", "refused", "node at", "rpc")
_CONFIG_KEYWORDS = ("config", "configuration", "settings file", "missing config")
_VALIDATION_KEYWORDS = ("valid", "missing", "required", "invalid", "must be", "no such", "not found")
_API_KEYWORDS = ("api", "http", "response", "status code", "endpoint returned", "request failed")


def _categorize(message: str, from_exception: Exception | None) -> type[CLIError]:
    """Pick the right CLIError subclass based on message keywords / exception type."""
    msg_lower = message.lower()

    # Check exception type first
    if from_exception is not None:
        exc_name = type(from_exception).__name__
        if exc_name == "NetworkError" or "Connection" in exc_name or "Timeout" in exc_name:
            return NetworkError
        if "Config" in exc_name or "Settings" in exc_name:
            return ConfigurationError
        if "Validation" in exc_name or "ValueError" in exc_name:
            return ValidationError

    # Keyword matching on message
    for kw in _NETWORK_KEYWORDS:
        if kw in msg_lower:
            return NetworkError
    for kw in _CONFIG_KEYWORDS:
        if kw in msg_lower:
            return ConfigurationError
    for kw in _VALIDATION_KEYWORDS:
        if kw in msg_lower:
            return ValidationError
    for kw in _API_KEYWORDS:
        if kw in msg_lower:
            return APIError

    return CLIError


# ---------------------------------------------------------------------------
# abort() — the canonical way to signal an error from a command
# ---------------------------------------------------------------------------


def abort(
    ctx: click.Context | None,
    message: str,
    *,
    error_type: type[CLIError] | None = None,
    from_exception: Exception | None = None,
) -> None:
    """Print an error (respecting ``--output`` format) and raise a ``CLIError``.

    The raised ``CLIError`` is caught by ``main()`` which exits with the
    appropriate code — no traceback is shown.

    Args:
        ctx: Click context (used to read ``output_format``). ``None`` is safe.
        message: Human-facing error message.
        error_type: Specific ``CLIError`` subclass. If ``None``, auto-categorised.
        from_exception: Original exception (preserves cause chain, adds detail to JSON).

    Raises:
        CLIError: (or a subclass) — always.
    """
    if error_type is None:
        error_type = _categorize(message, from_exception)

    exc = error_type(message)
    if from_exception is not None:
        exc.__cause__ = from_exception

    # Determine output format
    fmt = "table"
    if ctx is not None and ctx.obj:
        fmt = ctx.obj.get("output_format", "table")

    if fmt in ("json", "yaml"):
        payload: dict[str, Any] = {
            "error": type(exc).__name__,
            "message": message,
            "exit_code": exc.exit_code,
        }
        if from_exception is not None:
            payload["cause"] = type(from_exception).__name__
            payload["detail"] = str(from_exception)
        click.echo(_json.dumps(payload, indent=2))
    else:
        error(message)

    raise exc from from_exception


# ---------------------------------------------------------------------------
# Decorators (kept for backward compatibility)
# ---------------------------------------------------------------------------


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
    operation: Callable, error_message: str = "Operation failed", default_return: Any = None, raise_on_error: bool = False
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
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return bool(url_pattern.match(url))


def validate_address(address: str) -> bool:
    """
    Validate AITBC/Ethereum address format.

    Delegates to :func:`aitbc.utils.validation.validate_address` for
    EIP-55 checksum validation and legacy address support.

    Args:
        address: Address string

    Returns:
        True if valid, False otherwise
    """
    from aitbc.utils.validation import validate_address as _validate_address

    return _validate_address(address)
