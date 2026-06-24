"""
Performance profiling utilities for AITBC
Provides profiling hooks for performance bottleneck identification
"""

import cProfile
import functools
import io
import pstats
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, overload

from .aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProfilingResult:
    """Result of a profiling operation"""

    function_name: str
    total_time: float
    call_count: int
    avg_time: float
    max_time: float
    min_time: float


class PerformanceProfiler:
    """
    Performance profiler for function execution time tracking.
    Tracks execution statistics for function calls.
    """

    def __init__(self):
        """Initialize performance profiler"""
        self._stats: dict[str, list] = defaultdict(list)
        self._enabled = True

    def enable(self) -> None:
        """Enable profiling"""
        self._enabled = True
        logger.info("Performance profiling enabled")

    def disable(self) -> None:
        """Disable profiling"""
        self._enabled = False
        logger.info("Performance profiling disabled")

    def record(self, function_name: str, execution_time: float) -> None:
        """
        Record execution time for a function

        Args:
            function_name: Name of the function
            execution_time: Execution time in seconds
        """
        if self._enabled:
            self._stats[function_name].append(execution_time)

    @overload
    def get_stats(self, function_name: str) -> ProfilingResult: ...
    @overload
    def get_stats(self, function_name: None = None) -> dict[str, ProfilingResult]: ...
    def get_stats(self, function_name: str | None = None) -> ProfilingResult | dict[str, ProfilingResult]:
        """
        Get profiling statistics for a function or all functions

        Args:
            function_name: Specific function name, or None for all functions

        Returns:
            ProfilingResult or dictionary of results
        """
        if function_name:
            times = self._stats.get(function_name, [])
            if not times:
                return ProfilingResult(
                    function_name=function_name, total_time=0, call_count=0, avg_time=0, max_time=0, min_time=0
                )
            return ProfilingResult(
                function_name=function_name,
                total_time=sum(times),
                call_count=len(times),
                avg_time=sum(times) / len(times),
                max_time=max(times),
                min_time=min(times),
            )
        else:
            return {name: self.get_stats(name) for name in self._stats}

    def clear_stats(self) -> None:
        """Clear all profiling statistics"""
        self._stats.clear()
        logger.info("Profiling statistics cleared")

    def print_stats(self, function_name: str | None = None) -> None:
        """
        Print profiling statistics to console

        Args:
            function_name: Specific function name, or None for all functions
        """
        if function_name:
            self._print_single_stat(self.get_stats(function_name))
        else:
            for name, stat in self.get_stats().items():
                logger.info("--- %s ---", name)
                self._print_single_stat(stat)

    def _print_single_stat(self, stat: ProfilingResult) -> None:
        """Print single profiling result"""
        logger.info("  Total time: %ss", stat.total_time)
        logger.info("  Call count: %s", stat.call_count)
        logger.info("  Avg time: %ss", stat.avg_time)
        logger.info("  Max time: %ss", stat.max_time)
        logger.info("  Min time: %ss", stat.min_time)


_global_profiler = PerformanceProfiler()


def profile_function(profiler: PerformanceProfiler | None = None):
    """
    Decorator to profile function execution time

    Args:
        profiler: Custom profiler instance, or None to use global profiler

    Returns:
        Decorated function with profiling
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.perf_counter()
                execution_time = end_time - start_time
                target_profiler = profiler or _global_profiler
                target_profiler.record(func.__name__, execution_time)

        return wrapper

    return decorator


@contextmanager
def profile_context(name: str, profiler: PerformanceProfiler | None = None):
    """
    Context manager for profiling code blocks

    Args:
        name: Name for the profiling context
        profiler: Custom profiler instance, or None to use global profiler

    Yields:
        None
    """
    target_profiler = profiler or _global_profiler
    start_time = time.perf_counter()
    try:
        yield
    finally:
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        target_profiler.record(name, execution_time)


def profile_cprofile(func: Callable) -> Callable:
    """
    Decorator to profile function using cProfile

    Args:
        func: Function to profile

    Returns:
        Decorated function with cProfile profiling
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        profiler = cProfile.Profile()
        profiler.enable()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            profiler.disable()
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
            ps.print_stats(10)
            logger.info("Profile for %s:\n%s", func.__name__, s.getvalue())

    return wrapper


def get_global_profiler() -> PerformanceProfiler:
    """
    Get the global performance profiler instance

    Returns:
        Global PerformanceProfiler instance
    """
    return _global_profiler


def enable_global_profiling() -> None:
    """Enable global performance profiling"""
    _global_profiler.enable()


def disable_global_profiling() -> None:
    """Disable global performance profiling"""
    _global_profiler.disable()


def get_profiling_summary() -> dict[str, ProfilingResult]:
    """
    Get summary of all profiling data

    Returns:
        Dictionary of profiling results
    """
    return _global_profiler.get_stats()


def print_profiling_summary() -> None:
    """Print summary of all profiling data"""
    _global_profiler.print_stats()


def clear_profiling_data() -> None:
    """Clear all profiling data"""
    _global_profiler.clear_stats()
