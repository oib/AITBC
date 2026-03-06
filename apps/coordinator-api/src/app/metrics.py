"""Prometheus metrics for the AITBC Coordinator API."""

from prometheus_client import Counter

# Marketplace API metrics
marketplace_requests_total = Counter(
    'marketplace_requests_total',
    'Total number of marketplace API requests',
    ['endpoint', 'method']
)

marketplace_errors_total = Counter(
    'marketplace_errors_total',
    'Total number of marketplace API errors',
    ['endpoint', 'method', 'error_type']
)
