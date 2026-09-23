"""Prometheus metrics for the AITBC Coordinator API."""

from prometheus_client import Counter

# Market API metrics
market_requests_total = Counter("market_requests_total", "Total number of market API requests", ["endpoint", "method"])

market_errors_total = Counter("market_errors_total", "Total number of market API errors", ["endpoint", "method", "error_type"])

# Governance/economic proposal API metrics
governance_requests_total = Counter(
    "governance_requests_total", "Total number of governance API requests", ["endpoint", "method"]
)

governance_errors_total = Counter(
    "governance_errors_total", "Total number of governance API errors", ["endpoint", "method", "error_type"]
)
