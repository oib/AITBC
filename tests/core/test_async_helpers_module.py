"""
Tests for AITBC async helpers module (async_helpers.py)
This module has 0% coverage and 192 statements.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

async_helpers = load_module_from_path(
    "aitbc.async_helpers",
    Path("/opt/aitbc/aitbc/async_helpers.py")
)


# ============================================================================
# Run Sync Tests
# ============================================================================

class TestRunSync:
    """Test run_sync function"""

    def test_run_sync(self):
        async def coro():
            return "result"

        result = asyncio.run(async_helpers.run_sync(coro()))
        assert result == "result"

    def test_run_sync_with_value(self):
        async def coro():
            return 42

        result = asyncio.run(async_helpers.run_sync(coro()))
        assert result == 42


# ============================================================================
# Gather With Concurrency Tests
# ============================================================================

class TestGatherWithConcurrency:
    """Test gather_with_concurrency function"""

    def test_gather_with_concurrency(self):
        async def coro(i):
            await asyncio.sleep(0.01)
            return i * 2

        coros = [coro(i) for i in range(10)]
        result = asyncio.run(async_helpers.gather_with_concurrency(coros, limit=3))
        assert result == [i * 2 for i in range(10)]

    def test_gather_with_concurrency_default_limit(self):
        async def coro(i):
            return i

        coros = [coro(i) for i in range(5)]
        result = asyncio.run(async_helpers.gather_with_concurrency(coros))
        assert result == [0, 1, 2, 3, 4]

    def test_gather_with_concurrency_single_item(self):
        async def coro():
            return "single"

        result = asyncio.run(async_helpers.gather_with_concurrency([coro()]))
        assert result == ["single"]

    def test_gather_with_concurrency_empty_list(self):
        result = asyncio.run(async_helpers.gather_with_concurrency([]))
        assert result == []


# ============================================================================
# Run With Timeout Tests
# ============================================================================

class TestRunWithTimeout:
    """Test run_with_timeout function"""

    def test_run_with_timeout_success(self):
        async def coro():
            await asyncio.sleep(0.01)
            return "success"

        result = asyncio.run(async_helpers.run_with_timeout(coro(), timeout=1.0))
        assert result == "success"

    def test_run_with_timeout_expired(self):
        async def coro():
            await asyncio.sleep(1.0)
            return "success"

        result = asyncio.run(async_helpers.run_with_timeout(coro(), timeout=0.01, default="timeout"))
        assert result == "timeout"

    def test_run_with_timeout_default_none(self):
        async def coro():
            await asyncio.sleep(1.0)
            return "success"

        result = asyncio.run(async_helpers.run_with_timeout(coro(), timeout=0.01))
        assert result is None

    def test_run_with_timeout_custom_default(self):
        async def coro():
            await asyncio.sleep(1.0)
            return "success"

        result = asyncio.run(async_helpers.run_with_timeout(coro(), timeout=0.01, default=42))
        assert result == 42


# ============================================================================
# Batch Process Tests
# ============================================================================

class TestBatchProcess:
    """Test batch_process function"""

    def test_batch_process(self):
        async def process(item):
            return item * 2

        items = [1, 2, 3, 4, 5]
        result = asyncio.run(async_helpers.batch_process(items, process, batch_size=2, delay=0))
        assert result == [2, 4, 6, 8, 10]

    def test_batch_process_with_delay(self):
        async def process(item):
            return item

        items = [1, 2, 3, 4, 5]
        result = asyncio.run(async_helpers.batch_process(items, process, batch_size=2, delay=0.01))
        assert result == [1, 2, 3, 4, 5]

    def test_batch_process_single_batch(self):
        async def process(item):
            return item

        items = [1, 2, 3]
        result = asyncio.run(async_helpers.batch_process(items, process, batch_size=10, delay=0))
        assert result == [1, 2, 3]

    def test_batch_process_empty_items(self):
        async def process(item):
            return item

        result = asyncio.run(async_helpers.batch_process([], process))
        assert result == []

    def test_batch_process_default_params(self):
        async def process(item):
            return item

        items = [1, 2, 3]
        result = asyncio.run(async_helpers.batch_process(items, process))
        assert result == [1, 2, 3]


# ============================================================================
# Sync To Async Tests
# ============================================================================

class TestSyncToAsync:
    """Test sync_to_async decorator"""

    def test_sync_to_async(self):
        @async_helpers.sync_to_async
        def sync_func(x):
            return x * 2

        async def test():
            result = await sync_func(5)
            return result

        result = asyncio.run(test())
        assert result == 10

    def test_sync_to_async_with_args(self):
        @async_helpers.sync_to_async
        def sync_func(a, b):
            return a + b

        async def test():
            result = await sync_func(3, 4)
            return result

        result = asyncio.run(test())
        assert result == 7

    def test_sync_to_async_with_kwargs(self):
        @async_helpers.sync_to_async
        def sync_func(x, multiplier=2):
            return x * multiplier

        async def test():
            result = await sync_func(5, multiplier=3)
            return result

        result = asyncio.run(test())
        assert result == 15


# ============================================================================
# Async To Sync Tests
# ============================================================================

class TestAsyncToSync:
    """Test async_to_sync decorator"""

    def test_async_to_sync(self):
        @async_helpers.async_to_sync
        async def async_func(x):
            await asyncio.sleep(0.01)
            return x * 2

        result = async_func(5)
        assert result == 10

    def test_async_to_sync_with_args(self):
        @async_helpers.async_to_sync
        async def async_func(a, b):
            await asyncio.sleep(0.01)
            return a + b

        result = async_func(3, 4)
        assert result == 7

    def test_async_to_sync_with_kwargs(self):
        @async_helpers.async_to_sync
        async def async_func(x, multiplier=2):
            await asyncio.sleep(0.01)
            return x * multiplier

        result = async_func(5, multiplier=3)
        assert result == 15


# ============================================================================
# Retry Async Tests
# ============================================================================

class TestRetryAsync:
    """Test retry_async function"""

    def test_retry_async_success_first_attempt(self):
        call_count = 0

        async def coro_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = asyncio.run(async_helpers.retry_async(coro_func))
        assert result == "success"
        assert call_count == 1

    def test_retry_async_success_after_retry(self):
        call_count = 0

        async def coro_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = asyncio.run(async_helpers.retry_async(coro_func, max_attempts=3))
        assert result == "success"
        assert call_count == 2

    def test_retry_async_max_attempts_exceeded(self):
        call_count = 0

        async def coro_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            asyncio.run(async_helpers.retry_async(coro_func, max_attempts=3))
        assert call_count == 3

    def test_retry_async_custom_delay(self):
        call_count = 0

        async def coro_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = asyncio.run(async_helpers.retry_async(coro_func, max_attempts=3, delay=0.01))
        assert result == "success"
        assert call_count == 2

    def test_retry_async_custom_backoff(self):
        call_count = 0

        async def coro_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return "success"

        result = asyncio.run(async_helpers.retry_async(coro_func, max_attempts=5, delay=0.01, backoff=1.5))
        assert result == "success"
        assert call_count == 3


# ============================================================================
# Wait For Condition Tests
# ============================================================================

class TestWaitForCondition:
    """Test wait_for_condition function"""

    def test_wait_for_condition_true_immediately(self):
        condition_met = False

        async def condition():
            nonlocal condition_met
            condition_met = True
            return True

        result = asyncio.run(async_helpers.wait_for_condition(condition, timeout=1.0))
        assert result is True

    def test_wait_for_condition_true_after_delay(self):
        call_count = 0

        async def condition():
            nonlocal call_count
            call_count += 1
            return call_count >= 3

        result = asyncio.run(async_helpers.wait_for_condition(condition, timeout=1.0, check_interval=0.01))
        assert result is True
        assert call_count == 3

    def test_wait_for_condition_timeout(self):
        async def condition():
            return False

        result = asyncio.run(async_helpers.wait_for_condition(condition, timeout=0.1, check_interval=0.01))
        assert result is False

    def test_wait_for_condition_custom_interval(self):
        call_count = 0

        async def condition():
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        result = asyncio.run(async_helpers.wait_for_condition(condition, timeout=1.0, check_interval=0.05))
        assert result is True

    def test_wait_for_condition_default_params(self):
        async def condition():
            return True

        result = asyncio.run(async_helpers.wait_for_condition(condition))
        assert result is True
