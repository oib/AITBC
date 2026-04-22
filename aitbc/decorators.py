"""
AITBC Common Decorators
Reusable decorators for common patterns in AITBC applications
"""

import time
import functools
from typing import Callable, Type, Any
from .exceptions import AITBCError


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_failure: Callable[[Exception], Any] = None
):
    """
    Retry a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch
        on_failure: Optional callback function called on final failure
        
    Returns:
        Decorated function that retries on failure
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        if on_failure:
                            on_failure(e)
                        raise
            
            raise last_exception if last_exception else AITBCError("Retry failed")
        
        return wrapper
    return decorator


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
        print(f"{func.__name__} executed in {execution_time:.4f} seconds")
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
    cache = {}
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = (func.__name__, args, frozenset(kwargs.items()))
            current_time = time.time()
            
            # Check if cached result exists and is not expired
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if current_time - timestamp < ttl:
                    return result
            
            # Call function and cache result
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


def handle_exceptions(
    default_return: Any = None,
    log_errors: bool = True,
    raise_on: tuple[Type[Exception], ...] = ()
):
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
            except raise_on as e:
                raise
            except Exception as e:
                if log_errors:
                    print(f"Error in {func.__name__}: {e}")
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
        print(f"{func.__name__} executed in {execution_time:.4f} seconds")
        return result
    
    return wrapper
