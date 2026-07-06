"""
AITBC Common Decorators
Reusable decorators for common patterns in AITBC applications
"""

import functools
import time
from collections.abc import Callable
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def timing(func: Callable) -> Callable:
    """
    Decorator to measure and log function execution time.

    Args:
        func: Function to time

    Returns:
        Decorated function that prints execution time
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        logger.info("%s executed in %s seconds", func.__name__, execution_time)
        return result

    return wrapper


def cache_result(ttl: int = 300):
    """
    Simple in-memory cache decorator with TTL.

    Args:
        ttl: Time to live for cached results in seconds

    Returns:
        Decorated function with caching
    """
    cache: dict[tuple[Any, ...], Any] = {}

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = (func.__name__, args, frozenset(kwargs.items()))
            current_time = time.time()
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if current_time - timestamp < ttl:
                    return result
            result = func(*args, **kwargs)
            cache[cache_key] = (result, current_time)
            return result

        return wrapper

    return decorator


def validate_args(*validators: Callable):
    """
    Decorator to validate function arguments.

    Args:
        *validators: Validation functions that raise ValueError on invalid input

    Returns:
        Decorated function with argument validation
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for validator in validators:
                validator(*args, **kwargs)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def handle_exceptions(default_return: Any = None, log_errors: bool = True, raise_on: tuple[type[Exception], ...] = ()):
    """
    Decorator to handle exceptions gracefully.

    Args:
        default_return: Value to return on exception
        log_errors: Whether to log errors
        raise_on: Tuple of exception types to still raise

    Returns:
        Decorated function with exception handling
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except raise_on:
                raise
            except Exception as e:
                if log_errors:
                    logger.error("Error in %s: %s", func.__name__, e)
                return default_return

        return wrapper

    return decorator


def async_timing(func: Callable) -> Callable:
    """
    Decorator to measure async function execution time.

    Args:
        func: Async function to time

    Returns:
        Decorated async function that prints execution time
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        logger.info("%s executed in %s seconds", func.__name__, execution_time)
        return result

    return wrapper
