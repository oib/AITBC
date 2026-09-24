"""
Shared middleware for AITBC services
"""

from .correlation import CorrelationIDMiddleware
from .cors import setup_cors
from .error_handler import ErrorHandlerMiddleware
from .legacy_paths import MARKETPLACE_PATH_ALIASES, LegacyPathRewriteMiddleware
from .performance import PerformanceLoggingMiddleware
from .prometheus_metrics import PrometheusMetricsMiddleware
from .request_id import RequestIDMiddleware
from .validation import RequestValidationMiddleware

__all__ = [
    "CorrelationIDMiddleware",
    "MARKETPLACE_PATH_ALIASES",
    "ErrorHandlerMiddleware",
    "LegacyPathRewriteMiddleware",
    "PerformanceLoggingMiddleware",
    "PrometheusMetricsMiddleware",
    "RequestIDMiddleware",
    "RequestValidationMiddleware",
    "setup_cors",
]
