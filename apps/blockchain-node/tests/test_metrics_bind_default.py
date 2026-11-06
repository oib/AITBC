"""Pins for the node metrics exporter bind default (#1187 follow-up).

The Prometheus exporter must default to loopback: the fleet binds
:9009 loopback-only live, and a ``0.0.0.0`` code default silently
re-exposes metrics on every fresh deployment. Remote scraping stays
available via the ``AITBC_NODE_METRICS_HOST`` env opt-in.
"""

from __future__ import annotations

import pytest


class _FakeServer:
    """Captures the bind address without opening a socket."""

    instances: list[tuple[object, object]] = []

    def __init__(self, addr, handler):  # noqa: ANN001, ANN204
        self.addr = addr
        self.daemon_threads = True
        _FakeServer.instances.append((addr, handler))

    def serve_forever(self) -> None:
        return None


@pytest.fixture()
def captured_binds(monkeypatch: pytest.MonkeyPatch):
    from aitbc_chain.observability import exporters

    _FakeServer.instances.clear()
    monkeypatch.setattr(exporters, "ThreadingHTTPServer", _FakeServer)
    monkeypatch.delenv("AITBC_NODE_METRICS_HOST", raising=False)
    monkeypatch.setenv("AITBC_NODE_METRICS_PORT", "0")
    exporters._exporter_instances.pop("prometheus", None)
    yield _FakeServer.instances
    exporters._exporter_instances.pop("prometheus", None)


def test_prometheus_default_bind_is_loopback(captured_binds) -> None:
    from aitbc_chain.observability import exporters

    exporters._initialize_prometheus()
    assert captured_binds, "exporter did not attempt a bind"
    host, port = captured_binds[-1][0]
    assert host == "127.0.0.1"
    assert port == 0


def test_prometheus_env_override_still_works(monkeypatch: pytest.MonkeyPatch, captured_binds) -> None:
    from aitbc_chain.observability import exporters

    monkeypatch.setenv("AITBC_NODE_METRICS_HOST", "10.0.0.5")
    exporters._initialize_prometheus()
    host, _port = captured_binds[-1][0]
    assert host == "10.0.0.5"
