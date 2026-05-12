"""
Tests for AITBC decorators
"""

import time
import pytest
from unittest.mock import patch
from aitbc.decorators import (
    retry,
    timing,
    cache_result,
    validate_args,
    handle_exceptions,
    async_timing,
)
from aitbc.exceptions import AITBCError


class TestRetry:
    """Tests for retry decorator"""

    def test_retry_succeeds_on_first_attempt(self):
        """Test retry when function succeeds on first attempt"""
        @retry(max_attempts=3)
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"

    def test_retry_succeeds_after_failure(self):
        """Test retry when function succeeds after initial failure"""
        attempts = [0]
        
        @retry(max_attempts=3, delay=0.01)
        def test_func():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("fail")
            return "success"
        
        result = test_func()
        assert result == "success"
        assert attempts[0] == 2

    def test_retry_exhausts_attempts(self):
        """Test retry when function fails after all attempts"""
        @retry(max_attempts=2, delay=0.01)
        def test_func():
            raise ValueError("fail")
        
        with pytest.raises(ValueError):
            test_func()

    def test_retry_with_specific_exception(self):
        """Test retry only catches specified exceptions"""
        @retry(max_attempts=2, delay=0.01, exceptions=(ValueError,))
        def test_func():
            raise TypeError("fail")
        
        with pytest.raises(TypeError):
            test_func()

    def test_retry_with_backoff(self):
        """Test retry with exponential backoff"""
        attempts = [0]
        
        @retry(max_attempts=3, delay=0.01, backoff=2.0)
        def test_func():
            attempts[0] += 1
            raise ValueError("fail")
        
        start_time = time.time()
        with pytest.raises(ValueError):
            test_func()
        elapsed = time.time() - start_time
        
        # Should have delays: 0.01 + 0.02 = 0.03 seconds minimum
        assert elapsed >= 0.03

    def test_retry_with_on_failure_callback(self):
        """Test retry with on_failure callback"""
        callback_called = [False]
        
        def on_fail(e):
            callback_called[0] = True
        
        @retry(max_attempts=2, delay=0.01, on_failure=on_fail)
        def test_func():
            raise ValueError("fail")
        
        with pytest.raises(ValueError):
            test_func()
        
        assert callback_called[0] is True


class TestTiming:
    """Tests for timing decorator"""

    @patch('aitbc.decorators.logger')
    def test_timing_logs_execution_time(self, mock_logger):
        """Test timing decorator logs execution time"""
        @timing
        def test_func():
            time.sleep(0.01)
            return "result"
        
        result = test_func()
        assert result == "result"
        mock_logger.info.assert_called_once()
        assert "executed in" in mock_logger.info.call_args[0][0]

    @patch('aitbc.decorators.logger')
    def test_timing_preserves_function_name(self, mock_logger):
        """Test timing decorator preserves function name"""
        @timing
        def my_function():
            return "result"
        
        assert my_function.__name__ == "my_function"


class TestCacheResult:
    """Tests for cache_result decorator"""

    def test_cache_result_caches_value(self):
        """Test cache_result caches function return value"""
        call_count = [0]
        
        @cache_result(ttl=60)
        def test_func(x):
            call_count[0] += 1
            return x * 2
        
        result1 = test_func(5)
        result2 = test_func(5)
        
        assert result1 == 10
        assert result2 == 10
        assert call_count[0] == 1  # Only called once due to cache

    def test_cache_result_different_args(self):
        """Test cache_result with different arguments"""
        call_count = [0]
        
        @cache_result(ttl=60)
        def test_func(x):
            call_count[0] += 1
            return x * 2
        
        test_func(5)
        test_func(10)
        
        assert call_count[0] == 2  # Called twice for different args

    def test_cache_result_ttl_expires(self):
        """Test cache_result TTL expires"""
        call_count = [0]
        
        @cache_result(ttl=0.1)  # 100ms TTL
        def test_func(x):
            call_count[0] += 1
            return x * 2
        
        test_func(5)
        time.sleep(0.15)  # Wait for TTL to expire
        test_func(5)
        
        assert call_count[0] == 2  # Called again after TTL expired

    def test_cache_result_with_kwargs(self):
        """Test cache_result with keyword arguments"""
        call_count = [0]
        
        @cache_result(ttl=60)
        def test_func(x, y=10):
            call_count[0] += 1
            return x + y
        
        test_func(5, y=10)
        test_func(5, y=10)
        
        assert call_count[0] == 1  # Cached


class TestValidateArgs:
    """Tests for validate_args decorator"""

    def test_validate_args_passes_valid(self):
        """Test validate_args passes when validators succeed"""
        def validator(x):
            if x < 0:
                raise ValueError("Must be positive")
        
        @validate_args(validator)
        def test_func(x):
            return x * 2
        
        result = test_func(5)
        assert result == 10

    def test_validate_args_fails_invalid(self):
        """Test validate_args fails when validators raise error"""
        def validator(x):
            if x < 0:
                raise ValueError("Must be positive")
        
        @validate_args(validator)
        def test_func(x):
            return x * 2
        
        with pytest.raises(ValueError):
            test_func(-5)

    def test_validate_args_multiple_validators(self):
        """Test validate_args with multiple validators"""
        def validator1(x):
            if x < 0:
                raise ValueError("Must be positive")
        
        def validator2(x):
            if x > 100:
                raise ValueError("Must be <= 100")
        
        @validate_args(validator1, validator2)
        def test_func(x):
            return x * 2
        
        with pytest.raises(ValueError):
            test_func(150)


class TestHandleExceptions:
    """Tests for handle_exceptions decorator"""

    @patch('aitbc.decorators.logger')
    def test_handle_exceptions_returns_default(self, mock_logger):
        """Test handle_exceptions returns default on exception"""
        @handle_exceptions(default_return="error")
        def test_func():
            raise ValueError("fail")
        
        result = test_func()
        assert result == "error"
        mock_logger.error.assert_called_once()

    @patch('aitbc.decorators.logger')
    def test_handle_exceptions_no_logging(self, mock_logger):
        """Test handle_exceptions with logging disabled"""
        @handle_exceptions(default_return="error", log_errors=False)
        def test_func():
            raise ValueError("fail")
        
        result = test_func()
        assert result == "error"
        mock_logger.error.assert_not_called()

    def test_handle_exceptions_raises_on_specified(self):
        """Test handle_exceptions still raises specified exceptions"""
        @handle_exceptions(default_return="error", raise_on=(ValueError,))
        def test_func():
            raise ValueError("fail")
        
        with pytest.raises(ValueError):
            test_func()

    def test_handle_exceptions_passes_on_success(self):
        """Test handle_exceptions passes through successful return"""
        @handle_exceptions(default_return="error")
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"


class TestAsyncTiming:
    """Tests for async_timing decorator"""

    @pytest.mark.asyncio
    @patch('aitbc.decorators.logger')
    async def test_async_timing_logs_execution_time(self, mock_logger):
        """Test async_timing decorator logs execution time"""
        @async_timing
        async def test_func():
            await asyncio.sleep(0.01)
            return "result"
        
        import asyncio
        result = await test_func()
        assert result == "result"
        mock_logger.info.assert_called_once()
        assert "executed in" in mock_logger.info.call_args[0][0]

    @pytest.mark.asyncio
    async def test_async_timing_preserves_function_name(self):
        """Test async_timing decorator preserves function name"""
        @async_timing
        async def my_function():
            return "result"
        
        assert my_function.__name__ == "my_function"
