"""Shared helpers for the dynamic-pricing modules.

The lazy numpy handle, the Decimal conversion helpers, and the expected
failure surface were module-level in ``dynamic_pricing.py``; they live here
so ``dynamic_pricing.py`` and its model/factors/market siblings share one
copy without an import cycle (issue #1860, phase 6 band split).
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError


class _LazyNumpy:
    """numpy on first attribute access, not at module import.

    This module sits in coordinator-api's startup import graph, where a
    top-level ``import numpy`` cost ~9.4s of import time plus numpy's RSS
    on every service start. The ~15 ``np.`` call sites below stay
    untouched: the first one triggers the real import and swaps the
    module into ``globals()`` so later lookups are direct.
    """

    def __getattr__(self, name: str) -> Any:
        import numpy as _np_real

        globals()["np"] = _np_real
        return getattr(_np_real, name)


if TYPE_CHECKING:
    import numpy as np
else:
    np = _LazyNumpy()


def _D(value: float | int | str | Decimal) -> Decimal:
    """Convert a numeric value to Decimal for financial arithmetic."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _serialize_decimals(data: dict[str, Any]) -> dict[str, Any]:
    """Convert Decimal values in a dict to str for JSON serialization."""
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()}


_OPS_ERRORS: tuple[type[BaseException], ...] = (
    ArithmeticError,
    AttributeError,
    ImportError,
    KeyError,
    OSError,
    RuntimeError,
    SQLAlchemyError,
    TypeError,
    ValueError,
)
