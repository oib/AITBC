"""
Tests for profiling utilities
"""

import time
from unittest.mock import patch

import pytest

from aitbc.profiling import (
    PerformanceProfiler,
    ProfilingResult,
    clear_profiling_data,
    disable_global_profiling,
    enable_global_profiling,
    get_global_profiler,
    get_profiling_summary,
    print_profiling_summary,
    profile_context,
    profile_cprofile,
    profile_function,
)


class TestProfilingResult:
    """Tests for ProfilingResult dataclass"""

    def test_creation(self):
        """Test ProfilingResult creation"""
        result = ProfilingResult(
            function_name="test_func",
            total_time=1.0,
            call_count=10,
            avg_time=0.1,
            max_time=0.2,
            min_time=0.05
        )

        assert result.function_name == "test_func"
        assert result.total_time == 1.0
        assert result.call_count == 10


class TestPerformanceProfiler:
    """Tests for PerformanceProfiler"""

    @patch('aitbc.profiling.logger')
    def test_initialization(self, mock_logger):
        """Test PerformanceProfiler initialization"""
        profiler = PerformanceProfiler()

        assert profiler._enabled is True
        assert len(profiler._stats) == 0

    @patch('aitbc.profiling.logger')
    def test_enable(self, mock_logger):
        """Test enable profiling"""
        profiler = PerformanceProfiler()
        profiler.disable()
        profiler.enable()

        assert profiler._enabled is True
        mock_logger.info.assert_called()

    @patch('aitbc.profiling.logger')
    def test_disable(self, mock_logger):
        """Test disable profiling"""
        profiler = PerformanceProfiler()
        profiler.disable()

        assert profiler._enabled is False
        mock_logger.info.assert_called()

    def test_record_enabled(self):
        """Test record when enabled"""
        profiler = PerformanceProfiler()

        profiler.record("test_func", 0.5)

        assert len(profiler._stats["test_func"]) == 1
        assert profiler._stats["test_func"][0] == 0.5

    def test_record_disabled(self):
        """Test record when disabled"""
        profiler = PerformanceProfiler()
        profiler.disable()

        profiler.record("test_func", 0.5)

        assert "test_func" not in profiler._stats

    def test_get_stats_single_function(self):
        """Test get_stats for single function"""
        profiler = PerformanceProfiler()
        profiler.record("test_func", 0.1)
        profiler.record("test_func", 0.2)
        profiler.record("test_func", 0.3)

        stats = profiler.get_stats("test_func")

        assert stats.function_name == "test_func"
        assert stats.call_count == 3
        assert stats.total_time == 0.6
        assert stats.avg_time == pytest.approx(0.2)
        assert stats.max_time == 0.3
        assert stats.min_time == 0.1

    def test_get_stats_no_data(self):
        """Test get_stats for function with no data"""
        profiler = PerformanceProfiler()

        stats = profiler.get_stats("nonexistent")

        assert stats.function_name == "nonexistent"
        assert stats.call_count == 0
        assert stats.total_time == 0

    def test_get_stats_all_functions(self):
        """Test get_stats for all functions"""
        profiler = PerformanceProfiler()
        profiler.record("func1", 0.1)
        profiler.record("func2", 0.2)

        stats = profiler.get_stats()

        assert "func1" in stats
        assert "func2" in stats
        assert len(stats) == 2

    @patch('aitbc.profiling.logger')
    def test_clear_stats(self, mock_logger):
        """Test clear_stats"""
        profiler = PerformanceProfiler()
        profiler.record("test_func", 0.5)

        profiler.clear_stats()

        assert len(profiler._stats) == 0
        mock_logger.info.assert_called()

    @patch('aitbc.profiling.logger')
    def test_print_stats_single(self, mock_logger):
        """Test print_stats for single function"""
        profiler = PerformanceProfiler()
        profiler.record("test_func", 0.1)

        profiler.print_stats("test_func")

        assert mock_logger.info.called

    @patch('aitbc.profiling.logger')
    def test_print_stats_all(self, mock_logger):
        """Test print_stats for all functions"""
        profiler = PerformanceProfiler()
        profiler.record("func1", 0.1)
        profiler.record("func2", 0.2)

        profiler.print_stats()

        assert mock_logger.info.call_count > 0


class TestProfileFunctionDecorator:
    """Tests for profile_function decorator"""

    def test_decorator_with_global_profiler(self):
        """Test decorator with global profiler"""
        @profile_function()
        def test_func():
            time.sleep(0.01)
            return "result"

        result = test_func()

        assert result == "result"
        global_profiler = get_global_profiler()
        stats = global_profiler.get_stats("test_func")
        assert stats.call_count == 1

    def test_decorator_with_custom_profiler(self):
        """Test decorator with custom profiler"""
        custom_profiler = PerformanceProfiler()

        @profile_function(profiler=custom_profiler)
        def test_func():
            time.sleep(0.01)
            return "result"

        result = test_func()

        assert result == "result"
        stats = custom_profiler.get_stats("test_func")
        assert stats.call_count == 1

    def test_decorator_preserves_function_name(self):
        """Test decorator preserves function name"""
        @profile_function()
        def test_func():
            return "result"

        assert test_func.__name__ == "test_func"


class TestProfileContext:
    """Tests for profile_context context manager"""

    def test_context_manager_with_global_profiler(self):
        """Test context manager with global profiler"""
        with profile_context("test_context"):
            time.sleep(0.01)

        global_profiler = get_global_profiler()
        stats = global_profiler.get_stats("test_context")
        assert stats.call_count == 1

    def test_context_manager_with_custom_profiler(self):
        """Test context manager with custom profiler"""
        custom_profiler = PerformanceProfiler()

        with profile_context("test_context", profiler=custom_profiler):
            time.sleep(0.01)

        stats = custom_profiler.get_stats("test_context")
        assert stats.call_count == 1

    def test_context_manager_records_time(self):
        """Test context manager records execution time"""
        custom_profiler = PerformanceProfiler()

        with profile_context("test_context", profiler=custom_profiler):
            time.sleep(0.01)

        stats = custom_profiler.get_stats("test_context")
        assert stats.total_time > 0.01


class TestProfileCProfile:
    """Tests for profile_cprofile decorator"""

    @patch('aitbc.profiling.logger')
    def test_cprofile_decorator(self, mock_logger):
        """Test cProfile decorator"""
        @profile_cprofile
        def test_func():
            time.sleep(0.01)
            return "result"

        result = test_func()

        assert result == "result"
        mock_logger.info.assert_called()

    def test_cprofile_preserves_function_name(self):
        """Test cProfile decorator preserves function name"""
        @profile_cprofile
        def test_func():
            return "result"

        assert test_func.__name__ == "test_func"


class TestGlobalProfilerFunctions:
    """Tests for global profiler functions"""

    def test_get_global_profiler_singleton(self):
        """Test get_global_profiler returns singleton"""
        profiler1 = get_global_profiler()
        profiler2 = get_global_profiler()

        assert profiler1 is profiler2

    @patch('aitbc.profiling.logger')
    def test_enable_global_profiling(self, mock_logger):
        """Test enable_global_profiling"""
        disable_global_profiling()
        enable_global_profiling()

        profiler = get_global_profiler()
        assert profiler._enabled is True

    @patch('aitbc.profiling.logger')
    def test_disable_global_profiling(self, mock_logger):
        """Test disable_global_profiling"""
        disable_global_profiling()

        profiler = get_global_profiler()
        assert profiler._enabled is False

    def test_get_profiling_summary(self):
        """Test get_profiling_summary"""
        profiler = get_global_profiler()
        profiler.record("test_func", 0.1)

        summary = get_profiling_summary()

        assert "test_func" in summary

    @patch('aitbc.profiling.logger')
    def test_print_profiling_summary(self, mock_logger):
        """Test print_profiling_summary"""
        profiler = get_global_profiler()
        profiler.record("test_func", 0.1)

        print_profiling_summary()

        assert mock_logger.info.called

    @patch('aitbc.profiling.logger')
    def test_clear_profiling_data(self, mock_logger):
        """Test clear_profiling_data"""
        profiler = get_global_profiler()
        profiler.record("test_func", 0.1)

        clear_profiling_data()

        assert len(profiler._stats) == 0
