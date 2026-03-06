"""Placeholder exporter registration for metrics/log sinks."""

from __future__ import annotations

from typing import Iterable

REGISTERED_EXPORTERS: list[str] = []


def register_exporters(exporters: Iterable[str]) -> None:
    """Attach exporters for observability pipelines.

    Real implementations might wire Prometheus registrations, log shippers,
    or tracing exporters. For now, we simply record the names to keep track
    of requested sinks.
    """
    REGISTERED_EXPORTERS.extend(exporters)
