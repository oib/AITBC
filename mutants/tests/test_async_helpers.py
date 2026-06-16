"""
Tests for async helpers utilities
"""

import asyncio

import pytest

from aitbc.async_helpers import (
    async_to_sync,
    batch_process,
    gather_with_concurrency,
    retry_async,
    run_sync,
    run_with_timeout,
    sync_to_async,
    wait_for_condition,
)


class TestRunSync:
    """Tests for run_sync function"""

    @pytest.mark.asyncio
    async def test_run_sync_returns_result(self):
        """Test run_sync returns coroutine result"""

        async def test_coro():
            return "result"

        result = await run_sync(test_coro())
        assert result == "result"

    @pytest.mark.asyncio
    async def test_run_sync_with_value(self):
        """Test run_sync with numeric value"""

        async def test_coro():
            return 42

        result = await run_sync(test_coro())
        assert result == 42


class TestGatherWithConcurrency:
    """Tests for gather_with_concurrency function"""

    @pytest.mark.asyncio
    async def test_gather_with_concurrency_basic(self):
        """Test gather_with_concurrency basic functionality"""

        async def coro(i):
            await asyncio.sleep(0.01)
            return i * 2

        coros = [coro(i) for i in range(5)]
        results = await gather_with_concurrency(coros, limit=2)

        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_gather_with_concurrency_default_limit(self):
        """Test gather_with_concurrency with default limit"""

        async def coro(i):
            await asyncio.sleep(0.01)
            return i

        coros = [coro(i) for i in range(5)]
        results = await gather_with_concurrency(coros)

        assert results == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_gather_with_concurrency_empty_list(self):
        """Test gather_with_concurrency with empty list"""
        results = await gather_with_concurrency([])
        assert results == []


class TestRunWithTimeout:
    """Tests for run_with_timeout function"""

    @pytest.mark.asyncio
    async def test_run_with_timeout_success(self):
        """Test run_with_timeout when coroutine completes before timeout"""

        async def test_coro():
            await asyncio.sleep(0.01)
            return "success"

        result = await run_with_timeout(test_coro(), timeout=1.0)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_run_with_timeout_expires(self):
        """Test run_with_timeout returns default on timeout"""

        async def test_coro():
            await asyncio.sleep(1.0)
            return "success"

        result = await run_with_timeout(test_coro(), timeout=0.01, default="timeout")
        assert result == "timeout"

    @pytest.mark.asyncio
    async def test_run_with_timeout_default_none(self):
        """Test run_with_timeout returns None on timeout when no default"""

        async def test_coro():
            await asyncio.sleep(1.0)
            return "success"

        result = await run_with_timeout(test_coro(), timeout=0.01)
        assert result is None


class TestBatchProcess:
    """Tests for batch_process function"""

    @pytest.mark.asyncio
    async def test_batch_process_basic(self):
        """Test batch_process basic functionality"""

        async def process_func(item):
            return item * 2

        items = [1, 2, 3, 4, 5]
        results = await batch_process(items, process_func, batch_size=2, delay=0.01)

        assert results == [2, 4, 6, 8, 10]

    @pytest.mark.asyncio
    async def test_batch_process_single_batch(self):
        """Test batch_process with single batch"""

        async def process_func(item):
            return item + 1

        items = [1, 2, 3]
        results = await batch_process(items, process_func, batch_size=10, delay=0.01)

        assert results == [2, 3, 4]

    @pytest.mark.asyncio
    async def test_batch_process_empty_list(self):
        """Test batch_process with empty list"""

        async def process_func(item):
            return item

        results = await batch_process([], process_func)
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_process_no_delay(self):
        """Test batch_process with no delay"""

        async def process_func(item):
            return item * 3

        items = [1, 2, 3]
        results = await batch_process(items, process_func, batch_size=2, delay=0)

        assert results == [3, 6, 9]


class TestSyncToAsync:
    """Tests for sync_to_async decorator"""

    @pytest.mark.asyncio
    async def test_sync_to_async_decorator(self):
        """Test sync_to_async decorator converts sync function"""

        @sync_to_async
        def sync_func(x):
            return x * 2

        result = await sync_func(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_sync_to_async_with_kwargs(self):
        """Test sync_to_async with keyword arguments"""

        @sync_to_async
        def sync_func(x, y=10):
            return x + y

        result = await sync_func(5, y=20)
        assert result == 25


class TestAsyncToSync:
    """Tests for async_to_sync decorator"""

    def test_async_to_sync_decorator(self):
        """Test async_to_sync decorator converts async function"""

        @async_to_sync
        async def async_func(x):
            await asyncio.sleep(0.01)
            return x * 2

        result = async_func(5)
        assert result == 10

    def test_async_to_sync_with_kwargs(self):
        """Test async_to_sync with keyword arguments"""

        @async_to_sync
        async def async_func(x, y=10):
            await asyncio.sleep(0.01)
            return x + y

        result = async_func(5, y=20)
        assert result == 25


class TestRetryAsync:
    """Tests for retry_async function"""

    @pytest.mark.asyncio
    async def test_retry_async_success_on_first_attempt(self):
        """Test retry_async succeeds on first attempt"""
        attempt_count = [0]

        async def failing_func():
            attempt_count[0] += 1
            return "success"

        result = await retry_async(failing_func, max_attempts=3)
        assert result == "success"
        assert attempt_count[0] == 1

    @pytest.mark.asyncio
    async def test_retry_async_success_after_retries(self):
        """Test retry_async succeeds after initial failures"""
        attempt_count = [0]

        async def failing_func():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ValueError("fail")
            return "success"

        result = await retry_async(failing_func, max_attempts=3, delay=0.01)
        assert result == "success"
        assert attempt_count[0] == 3

    @pytest.mark.asyncio
    async def test_retry_async_exhausts_attempts(self):
        """Test retry_async raises after exhausting attempts"""
        attempt_count = [0]

        async def failing_func():
            attempt_count[0] += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await retry_async(failing_func, max_attempts=2, delay=0.01)

        assert attempt_count[0] == 2

    @pytest.mark.asyncio
    async def test_retry_async_with_backoff(self):
        """Test retry_async with exponential backoff"""
        attempt_count = [0]

        async def failing_func():
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise ValueError("fail")
            return "success"

        start_time = asyncio.get_event_loop().time()
        result = await retry_async(failing_func, max_attempts=3, delay=0.05, backoff=2.0)
        elapsed = asyncio.get_event_loop().time() - start_time

        assert result == "success"
        assert elapsed >= 0.05  # Should have at least one delay


class TestWaitForCondition:
    """Tests for wait_for_condition function"""

    @pytest.mark.asyncio
    async def test_wait_for_condition_true_immediately(self):
        """Test wait_for_condition when condition is true immediately"""

        async def condition():
            return True

        result = await wait_for_condition(condition, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_condition_becomes_true(self):
        """Test wait_for_condition when condition becomes true"""
        attempt_count = [0]

        async def condition():
            attempt_count[0] += 1
            return attempt_count[0] >= 3

        result = await wait_for_condition(condition, timeout=1.0, check_interval=0.05)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_condition_timeout(self):
        """Test wait_for_condition returns False on timeout"""

        async def condition():
            return False

        result = await wait_for_condition(condition, timeout=0.1, check_interval=0.01)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_condition_default_interval(self):
        """Test wait_for_condition with default check interval"""

        async def condition():
            return True

        result = await wait_for_condition(condition, timeout=1.0)
        assert result is True
