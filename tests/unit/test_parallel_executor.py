"""Unit tests for aitbc.parallel.executor (A2)."""

import time

import pytest

from aitbc.parallel.executor import ParallelExecutor


@pytest.fixture(autouse=True)
def _cleanup_executor():
    """Ensure executor is cleaned up after each test."""
    yield
    # Cleanup is handled by explicit close() calls in tests


class TestExecuteGroups:
    def test_execute_groups_parallel(self) -> None:
        """3 groups, verify results in correct order."""
        executor = ParallelExecutor(max_workers=4)
        try:
            groups = [["a", "b"], ["c"], ["d", "e"]]
            results = executor.execute_groups(groups, lambda x: x.upper())
            assert results == [["A", "B"], ["C"], ["D", "E"]]
        finally:
            executor.close()

    def test_empty_groups(self) -> None:
        """Empty input → empty output."""
        executor = ParallelExecutor(max_workers=2)
        try:
            results = executor.execute_groups([], lambda x: x)
            assert results == []
        finally:
            executor.close()

    def test_single_group(self) -> None:
        """1 group of 5 tasks → 1 result list of 5."""
        executor = ParallelExecutor(max_workers=4)
        try:
            groups = [["t1", "t2", "t3", "t4", "t5"]]
            results = executor.execute_groups(groups, lambda x: f"processed_{x}")
            assert results == [["processed_t1", "processed_t2", "processed_t3", "processed_t4", "processed_t5"]]
        finally:
            executor.close()

    def test_empty_group_within_list(self) -> None:
        """A group that is an empty list → empty result list."""
        executor = ParallelExecutor(max_workers=2)
        try:
            groups = [["a"], [], ["b"]]
            results = executor.execute_groups(groups, lambda x: x.upper())
            assert results == [["A"], [], ["B"]]
        finally:
            executor.close()

    def test_deterministic_results(self) -> None:
        """Same input always produces same output (no race conditions in ordering)."""
        executor = ParallelExecutor(max_workers=4)
        try:
            groups = [["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"]]
            expected = executor.execute_groups(groups, lambda x: f"r_{x}")
            # Run 10 times — all must produce identical results
            for _ in range(10):
                results = executor.execute_groups(groups, lambda x: f"r_{x}")
                assert results == expected
        finally:
            executor.close()

    def test_results_preserve_input_order(self) -> None:
        """Results are in input order even if tasks complete out of order."""
        executor = ParallelExecutor(max_workers=4)
        try:
            # Tasks with varying sleep times to force out-of-order completion
            def slow_fn(x: str) -> str:
                time.sleep(0.01 if x == "slow" else 0)
                return x

            groups = [["fast1", "slow", "fast2", "fast3"]]
            results = executor.execute_groups(groups, slow_fn)
            # Results must be in input order, not completion order
            assert results == [["fast1", "slow", "fast2", "fast3"]]
        finally:
            executor.close()


class TestExecuteSequential:
    def test_execute_sequential(self) -> None:
        """Fallback path: execute items sequentially."""
        executor = ParallelExecutor(max_workers=4)
        try:
            items = ["a", "b", "c"]
            results = executor.execute_sequential(items, lambda x: x.upper())
            assert results == ["A", "B", "C"]
        finally:
            executor.close()

    def test_execute_sequential_empty(self) -> None:
        executor = ParallelExecutor(max_workers=2)
        try:
            assert executor.execute_sequential([], lambda x: x) == []
        finally:
            executor.close()


class TestClose:
    def test_close_cleanup(self) -> None:
        """Executor closes cleanly."""
        executor = ParallelExecutor(max_workers=2)
        executor.execute_groups([["a", "b"]], lambda x: x)
        executor.close()
        # After close, internal executor is None
        assert executor._executor is None

    def test_close_idempotent(self) -> None:
        """Close can be called multiple times without error."""
        executor = ParallelExecutor(max_workers=2)
        executor.close()
        executor.close()  # should not raise


class TestLazyInit:
    def test_lazy_init(self) -> None:
        """Thread pool is not created until first use."""
        executor = ParallelExecutor(max_workers=2)
        assert executor._executor is None
        executor.execute_groups([["a"]], lambda x: x)
        assert executor._executor is not None
        executor.close()
