"""
Parallel executor with deterministic result ordering.

Executes groups of tasks in parallel using a thread pool. Within each group,
tasks are executed in parallel. Groups are executed sequentially to preserve
dependency ordering. Results are returned in the same structure as the input,
preserving determinism.
"""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TypeVar

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class ParallelExecutor:
    """Executes groups of tasks in parallel with deterministic result ordering.

    Each group is executed as a batch of parallel tasks. Results are returned
    in the same order as the input groups, preserving determinism.

    Usage::

        executor = ParallelExecutor(max_workers=4)
        groups = [["tx1", "tx2"], ["tx3"]]  # group 1: parallel, group 2: after
        results = executor.execute_groups(groups, lambda tx: validate(tx))
        # results = [["ok", "ok"], ["ok"]]
        executor.close()
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None

    def _get_executor(self) -> ThreadPoolExecutor:
        """Lazy-init the thread pool."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
            logger.info("ParallelExecutor initialized with %d workers", self._max_workers)
        return self._executor

    def execute_groups(
        self,
        groups: list[list[T]],
        fn: Callable[[T], R],
    ) -> list[list[R]]:
        """Execute groups of tasks in parallel.

        Within each group, tasks are executed in parallel (thread pool).
        Groups are executed sequentially (group 1, then group 2, etc.)
        to preserve dependency ordering.

        Returns results in the same structure as input: list of lists,
        where results[i][j] = fn(groups[i][j]).
        """
        executor = self._get_executor()
        results: list[list[R]] = []

        for group in groups:
            if not group:
                results.append([])
                continue

            # Submit all tasks in this group in parallel
            future_to_index: dict[Future[R], int] = {}
            for tx_idx, item in enumerate(group):
                future = executor.submit(fn, item)
                future_to_index[future] = tx_idx

            # Collect results in input order (deterministic)
            group_results: list[R] = [None] * len(group)  # type: ignore[list-item]
            for future in as_completed(future_to_index):
                tx_idx = future_to_index[future]
                group_results[tx_idx] = future.result()

            results.append(group_results)

        return results

    def execute_sequential(
        self,
        items: list[T],
        fn: Callable[[T], R],
    ) -> list[R]:
        """Fallback: execute items sequentially. Returns results in order."""
        return [fn(item) for item in items]

    def close(self) -> None:
        """Shut down the thread pool."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
            logger.info("ParallelExecutor shut down")
