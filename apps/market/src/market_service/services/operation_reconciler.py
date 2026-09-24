"""Operation ledger reconciler for the market service.

The implementation moved to :mod:`aitbc.operation_reconciler` so the
coordinator can run the same sweeper; this module keeps the historical
import path and the ``MARKET_OPS_*`` env names.
"""

from __future__ import annotations

from collections.abc import Callable

from aitbc.operation_reconciler import OperationReconciler as _SharedReconciler
from aitbc.operations import OperationLedger


class OperationReconciler(_SharedReconciler):
    def __init__(
        self,
        ledger_factory: Callable[[], OperationLedger],
        interval_seconds: int | None = None,
        retention_seconds: int | None = None,
    ) -> None:
        super().__init__(
            ledger_factory,
            interval_seconds=interval_seconds,
            retention_seconds=retention_seconds,
            env_prefix="MARKET_OPS",
        )


__all__ = ["OperationReconciler"]
