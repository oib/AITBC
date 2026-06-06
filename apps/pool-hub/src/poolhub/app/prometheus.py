from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

match_requests_total = Counter(
    "poolhub_match_requests_total",
    "Total number of match requests received",
)
match_candidates_returned = Counter(
    "poolhub_match_candidates_total",
    "Total number of candidates returned",
)
match_failures_total = Counter(
    "poolhub_match_failures_total",
    "Total number of match request failures",
)
match_latency_seconds = Histogram(
    "poolhub_match_latency_seconds",
    "Latency of match processing",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
miners_online_gauge = Gauge(
    "poolhub_miners_online",
    "Number of miners considered online",
)


def render_metrics() -> tuple[str, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def reset_metrics() -> None:
    match_requests_total._value.set(0)  # type: ignore[attr-defined]
    match_candidates_returned._value.set(0)  # type: ignore[attr-defined]
    match_failures_total._value.set(0)  # type: ignore[attr-defined]
    match_latency_seconds._sum.set(0)  # type: ignore[attr-defined]
    match_latency_seconds._count.set(0)  # type: ignore[attr-defined]
    match_latency_seconds._samples = []  # type: ignore[attr-defined]
    miners_online_gauge._value.set(0)  # type: ignore[attr-defined]
