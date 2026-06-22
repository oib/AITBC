"""
AITBC Data Layer Module
Data abstraction for AITBC applications
"""

from typing import Any
from collections.abc import Callable

from aitbc.data_layer.data_layer import (
    DataLayer,
    MockDataGenerator,
)

try:
    from aitbc.data_layer.data_layer import RealDataFetcher, get_data_layer
except ImportError:
    RealDataFetcher: type | None = None  # type: ignore[no-redef]
    get_data_layer: Callable[..., Any] | None = None  # type: ignore[no-redef]

__all__ = [
    "DataLayer",
    "MockDataGenerator",
    "RealDataFetcher",
    "get_data_layer",
]
