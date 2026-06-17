"""
AITBC Data Layer Module
Data abstraction for AITBC applications
"""

from aitbc.data_layer.data_layer import (
    DataLayer,
    MockDataGenerator,
)

try:
    from aitbc.data_layer.data_layer import RealDataFetcher, get_data_layer
except ImportError:
    RealDataFetcher = None  # type: ignore[misc,assignment]
    get_data_layer = None  # type: ignore[misc,assignment]

__all__ = [
    "DataLayer",
    "MockDataGenerator",
    "RealDataFetcher",
    "get_data_layer",
]
