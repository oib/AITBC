"""
Tests for AITBC decorators module (decorators.py)
This module has 0% coverage and 191 statements.
"""

import asyncio
import importlib.util
import time
from pathlib import Path

import pytest


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decorators = load_module_from_path("aitbc.decorators", Path("/opt/aitbc/aitbc/decorators/decorators.py"))


# ============================================================================
# Retry Decorator Tests
# ============================================================================


class TestRetryDecorator:
    """Test retry decorator"""

    def test_retry_success_first_attempt(self):
        call_count = 0

        @decorators.retry(max_attempts=3, delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_success_after_retry(self):
        call_count = 0

        @decorators.retry(max_attempts=3, delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 2

    def test_retry_max_attempts_exceeded(self):
        call_count = 0

        @decorators.retry(max_attempts=3, delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            test_func()
        assert call_count == 3

    def test_retry_custom_delay(self):
        call_count = 0

        @decorators.retry(max_attempts=3, delay=0.01, backoff=1.5)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 2

    def test_retry_specific_exception(self):
        call_count = 0

        @decorators.retry(max_attempts=3, delay=0.01, exceptions=(ValueError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = test_func()
        assert result == "success"

    def test_retry_uncaught_exception(self):
        @decorators.retry(max_attempts=3, delay=0.01, exceptions=(ValueError,))
        def test_func():
            raise TypeError("different error")

        with pytest.raises(TypeError):
            test_func()

    def test_retry_with_on_failure_callback(self):
        failure_called = False

        def on_failure(e):
            nonlocal failure_called
            failure_called = True

        @decorators.retry(max_attempts=2, delay=0.01, on_failure=on_failure)
        def test_func():
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            test_func()
        assert failure_called is True

    def test_retry_defaults(self):
        @decorators.retry()
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"


# ============================================================================
# Timing Decorator Tests
# ============================================================================


class TestTimingDecorator:
    """Test timing decorator"""

    def test_timing_decorator(self):
        @decorators.timing
        def test_func():
            time.sleep(0.01)
            return "result"

        result = test_func()
        assert result == "result"

    def test_timing_decorator_with_args(self):
        @decorators.timing
        def test_func(a, b):
            return a + b

        result = test_func(3, 4)
        assert result == 7

    def test_timing_decorator_with_kwargs(self):
        @decorators.timing
        def test_func(x, multiplier=2):
            return x * multiplier

        result = test_func(5, multiplier=3)
        assert result == 15


# ============================================================================
# Cache Result Decorator Tests
# ============================================================================


class TestCacheResultDecorator:
    """Test cache_result decorator"""

    def test_cache_result_decorator(self):
        call_count = 0

        @decorators.cache_result(ttl=1)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call
        result1 = test_func(5)
        assert result1 == 10
        assert call_count == 1

        # Second call should use cache
        result2 = test_func(5)
        assert result2 == 10
        assert call_count == 1  # Should not increment

    def test_cache_result_different_args(self):
        call_count = 0

        @decorators.cache_result(ttl=1)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        test_func(5)
        test_func(10)
        assert call_count == 2  # Different args, no cache hit

    def test_cache_result_with_kwargs(self):
        call_count = 0

        @decorators.cache_result(ttl=1)
        def test_func(x, multiplier=2):
            nonlocal call_count
            call_count += 1
            return x * multiplier

        test_func(5, multiplier=2)
        test_func(5, multiplier=2)
        assert call_count == 1  # Same args, cache hit

    def test_cache_result_expiration(self):
        call_count = 0

        @decorators.cache_result(ttl=0.01)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        test_func(5)
        time.sleep(0.02)
        test_func(5)
        assert call_count == 2  # Cache expired

    def test_cache_result_default_ttl(self):
        call_count = 0

        @decorators.cache_result()
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        test_func(5)
        test_func(5)
        assert call_count == 1  # Should use cache


# ============================================================================
# Validate Args Decorator Tests
# ============================================================================


class TestValidateArgsDecorator:
    """Test validate_args decorator"""

    def test_validate_args_valid(self):
        def validator(x):
            if x < 0:
                raise ValueError("x must be positive")

        @decorators.validate_args(validator)
        def test_func(x):
            return x * 2

        result = test_func(5)
        assert result == 10

    def test_validate_args_invalid(self):
        def validator(x):
            if x < 0:
                raise ValueError("x must be positive")

        @decorators.validate_args(validator)
        def test_func(x):
            return x * 2

        with pytest.raises(ValueError):
            test_func(-5)

    def test_validate_args_multiple_validators(self):
        def validator1(x):
            if x < 0:
                raise ValueError("x must be positive")

        def validator2(x):
            if x > 100:
                raise ValueError("x must be <= 100")

        @decorators.validate_args(validator1, validator2)
        def test_func(x):
            return x * 2

        result = test_func(50)
        assert result == 100

    def test_validate_args_multiple_validators_fail(self):
        def validator1(x):
            if x < 0:
                raise ValueError("x must be positive")

        def validator2(x):
            if x > 100:
                raise ValueError("x must be <= 100")

        @decorators.validate_args(validator1, validator2)
        def test_func(x):
            return x * 2

        with pytest.raises(ValueError):
            test_func(150)

    def test_validate_args_no_validators(self):
        @decorators.validate_args()
        def test_func(x):
            return x * 2

        result = test_func(5)
        assert result == 10


# ============================================================================
# Handle Exceptions Decorator Tests
# ============================================================================


class TestHandleExceptionsDecorator:
    """Test handle_exceptions decorator"""

    def test_handle_exceptions_no_error(self):
        @decorators.handle_exceptions(default_return="error")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_handle_exceptions_with_error(self):
        @decorators.handle_exceptions(default_return="error")
        def test_func():
            raise ValueError("test error")

        result = test_func()
        assert result == "error"

    def test_handle_exceptions_no_default(self):
        @decorators.handle_exceptions()
        def test_func():
            raise ValueError("test error")

        result = test_func()
        assert result is None

    def test_handle_exceptions_log_errors_false(self):
        @decorators.handle_exceptions(default_return="error", log_errors=False)
        def test_func():
            raise ValueError("test error")

        result = test_func()
        assert result == "error"

    def test_handle_exceptions_raise_on(self):
        @decorators.handle_exceptions(default_return="error", raise_on=(ValueError,))
        def test_func():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            test_func()

    def test_handle_exceptions_raise_on_different_error(self):
        @decorators.handle_exceptions(default_return="error", raise_on=(ValueError,))
        def test_func():
            raise TypeError("different error")

        result = test_func()
        assert result == "error"


# ============================================================================
# Async Timing Decorator Tests
# ============================================================================


class TestAsyncTimingDecorator:
    """Test async_timing decorator"""

    def test_async_timing_decorator(self):
        @decorators.async_timing
        async def test_func():
            await asyncio.sleep(0.01)
            return "result"

        result = asyncio.run(test_func())
        assert result == "result"

    def test_async_timing_decorator_with_args(self):
        @decorators.async_timing
        async def test_func(a, b):
            await asyncio.sleep(0.01)
            return a + b

        result = asyncio.run(test_func(3, 4))
        assert result == 7

    def test_async_timing_decorator_with_kwargs(self):
        @decorators.async_timing
        async def test_func(x, multiplier=2):
            await asyncio.sleep(0.01)
            return x * multiplier

        result = asyncio.run(test_func(5, multiplier=3))
        assert result == 15
