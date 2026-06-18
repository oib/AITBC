"""
Queue Decorators Module
Provides debounce and throttle decorators for rate limiting
"""

import asyncio
from collections.abc import Callable


def debounce(delay: float = 0.5):
    """Decorator to debounce function calls"""

    def decorator(func: Callable) -> Callable:
        last_called = [0]
        timer = [None]

        async def wrapped(*args, **kwargs):
            async def call():
                await asyncio.sleep(delay)
                if asyncio.get_event_loop().time() - last_called[0] >= delay:
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)

            last_called[0] = asyncio.get_event_loop().time()
            if timer[0]:
                timer[0].cancel()
            timer[0] = asyncio.create_task(call())
            return await timer[0]

        return wrapped

    return decorator


def throttle(calls_per_second: float = 1.0):
    """Decorator to throttle function calls"""

    def decorator(func: Callable) -> Callable:
        min_interval = 1.0 / calls_per_second
        last_called = [0]

        async def wrapped(*args, **kwargs):
            now = asyncio.get_event_loop().time()
            elapsed = now - last_called[0]
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            last_called[0] = asyncio.get_event_loop().time()
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        return wrapped

    return decorator
