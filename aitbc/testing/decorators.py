"""
Test Decorators and Helpers Module
Provides decorators and test scenario helpers
"""

import asyncio
from collections.abc import Callable
from typing import Any

from aitbc.aitbc_logging import get_logger
from .factories import MockFactory

logger = get_logger(__name__)


def mock_async_call(return_value: Any = None, delay: float = 0):
    """Decorator to mock async calls with optional delay"""

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            if delay > 0:
                await asyncio.sleep(delay)
            return return_value

        return wrapper

    return decorator


def create_mock_config(**overrides) -> dict[str, Any]:
    """Create mock configuration"""
    config = {
        "debug": False,
        "log_level": "INFO",
        "database_url": "sqlite:///test.db",
        "redis_url": "redis://localhost:6379",
        "api_host": "localhost",
        "api_port": 8080,
        "secret_key": MockFactory.generate_string(32),
        "max_workers": 4,
        "timeout": 30,
    }
    config.update(overrides)
    return config


def create_test_scenario(name: str, steps: list[Callable]) -> Callable:
    """Create a test scenario with multiple steps"""

    def scenario():
        logger.info("Running test scenario", name=name)
        results = []
        for i, step in enumerate(steps):
            try:
                result = step()
                results.append({"step": i + 1, "status": "passed", "result": result})
            except Exception as e:
                results.append({"step": i + 1, "status": "failed", "error": str(e)})
        return results

    return scenario
