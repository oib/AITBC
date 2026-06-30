"""Consensus Prometheus metrics (v0.7.5 B12).

Registers gauges/counters/histograms for multi-validator consensus
observability. Metrics are registered lazily on first import to avoid
duplicate-registration errors in test environments.
"""

from __future__ import annotations

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

_METRICS: dict[str, Any] = {}
_REGISTERED = False


def _register_metrics() -> None:
    """Register Prometheus metrics (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        from prometheus_client import Counter, Gauge, Histogram

        _METRICS["consensus_validators_active"] = Gauge(
            "consensus_validators_active",
            "Number of active validators in the consensus set",
        )
        _METRICS["consensus_validators_total"] = Gauge(
            "consensus_validators_total",
            "Total number of validators (active + inactive)",
        )
        _METRICS["consensus_rounds_total"] = Counter(
            "consensus_rounds_total",
            "Total consensus rounds attempted",
        )
        _METRICS["consensus_rounds_successful_total"] = Counter(
            "consensus_rounds_successful_total",
            "Consensus rounds that reached commit phase",
        )
        _METRICS["consensus_view_changes_total"] = Counter(
            "consensus_view_changes_total",
            "View changes triggered",
        )
        _METRICS["consensus_byzantine_detections_total"] = Counter(
            "consensus_byzantine_detections_total",
            "Byzantine validators detected",
        )
        _METRICS["consensus_slashing_events_total"] = Counter(
            "consensus_slashing_events_total",
            "Slashing events applied",
        )
        _METRICS["consensus_round_duration_seconds"] = Histogram(
            "consensus_round_duration_seconds",
            "Time per consensus round in seconds",
        )
        _REGISTERED = True
    except ImportError:
        logger.warning("prometheus_client not installed, consensus metrics disabled")
    except Exception as e:
        logger.warning("Failed to register consensus metrics: %s", e)


def update_consensus_metrics(metrics: dict[str, Any]) -> None:
    """Update Prometheus metrics from a consensus metrics dict.

    Called periodically by the metrics collector with the output of
    ``MultiValidatorPoA.collect_metrics()``.
    """
    _register_metrics()
    if not _REGISTERED:
        return
    for name, value in metrics.items():
        metric = _METRICS.get(name)
        if metric is None:
            continue
        try:
            if hasattr(metric, "set"):  # Gauge
                metric.set(value)
            elif hasattr(metric, "inc"):  # Counter
                metric.inc(value - 0 if value else 0)
        except Exception:
            pass


def observe_round_duration(seconds: float) -> None:
    """Record a consensus round duration in the histogram."""
    _register_metrics()
    hist = _METRICS.get("consensus_round_duration_seconds")
    if hist is not None:
        try:
            hist.observe(seconds)
        except Exception:
            pass


def get_registered_metrics() -> dict[str, Any]:
    """Return the registered metric objects (for testing)."""
    _register_metrics()
    return _METRICS
