"""
AITBC Async Helpers
Async utilities for AITBC applications
"""

import asyncio
from typing import Coroutine, Any, List, TypeVar, Callable
from functools import wraps

T = TypeVar('T')


async def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run a coroutine from synchronous code.
    
    Args:
        coro: Coroutine to run
        
    Returns:
        Result of the coroutine
    """
    return await asyncio.create_task(coro)


async def gather_with_concurrency(
    coros: List[Coroutine[Any, Any, T]],
    limit: int = 10
) -> List[T]:
    """
    Gather coroutines with concurrency limit.
    
    Args:
        coros: List of coroutines to execute
        limit: Maximum concurrent coroutines
        
    Returns:
        List of results from all coroutines
    """
    semaphore = asyncio.Semaphore(limit)
    
    async def limited_coro(coro: Coroutine[Any, Any, T]) -> T:
        async with semaphore:
            return await coro
    
    limited_coros = [limited_coro(coro) for coro in coros]
    return await asyncio.gather(*limited_coros)


async def run_with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout: float,
    default: T = None
) -> T:
    """
    Run a coroutine with a timeout.
    
    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        default: Default value if timeout occurs
        
    Returns:
        Result of coroutine or default value on timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


async def batch_process(
    items: List[Any],
    process_func: Callable[[Any], Coroutine[Any, Any, T]],
    batch_size: int = 10,
    delay: float = 0.1
) -> List[T]:
    """
    Process items in batches with delay between batches.
    
    Args:
        items: Items to process
        process_func: Async function to process each item
        batch_size: Number of items per batch
        delay: Delay between batches in seconds
        
    Returns:
        List of results
    """
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = await asyncio.gather(*[process_func(item) for item in batch])
        results.extend(batch_results)
        
        if i + batch_size < len(items):
            await asyncio.sleep(delay)
    
    return results


def sync_to_async(func: Callable) -> Callable:
    """
    Decorator to convert a synchronous function to async.
    
    Args:
        func: Synchronous function to convert
        
    Returns:
        Async wrapper function
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def async_to_sync(func: Callable) -> Callable:
    """
    Decorator to convert an async function to sync.
    
    Args:
        func: Async function to convert
        
    Returns:
        Synchronous wrapper function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper


async def retry_async(
    coro_func: Callable,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0
) -> Any:
    """
    Retry an async coroutine with exponential backoff.
    
    Args:
        coro_func: Function that returns a coroutine
        max_attempts: Maximum retry attempts
        delay: Initial delay in seconds
        backoff: Multiplier for delay after each retry
        
    Returns:
        Result of the coroutine
    """
    last_exception = None
    current_delay = delay
    
    for attempt in range(max_attempts):
        try:
            return await coro_func()
        except Exception as e:
            last_exception = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(current_delay)
                current_delay *= backoff
    
    raise last_exception


async def wait_for_condition(
    condition: Callable[[], Coroutine[Any, Any, bool]],
    timeout: float = 30.0,
    check_interval: float = 0.5
) -> bool:
    """
    Wait for a condition to become true.
    
    Args:
        condition: Async function that returns a boolean
        timeout: Maximum wait time in seconds
        check_interval: Time between checks in seconds
        
    Returns:
        True if condition became true, False if timeout
    """
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        if await condition():
            return True
        await asyncio.sleep(check_interval)
    
    return False
