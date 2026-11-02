"""Is the service a URL names reachable? The test suites' auto-skip probes build on this.

``requires_redis`` / ``requires_postgres`` tests skip when nothing listens at the
configured ``REDIS_URL`` / ``DATABASE_URL``. The first probes cut the host part out
of the URL with ``rest.split("/", 0)``: a maxsplit of 0 splits nothing, so any URL
with a ``/db`` path (``postgresql://localhost:5432/aitbc``, the probe's own default)
kept the path in the port, ``int()`` raised, and the broad ``except`` answered "not
available" -- every marked test skipped even with the server up. ``urlsplit`` takes
the URL apart properly.
"""

from __future__ import annotations

import socket
from urllib.parse import urlsplit


def url_host_port(url: str, default_port: int) -> tuple[str, int] | None:
    """Host and TCP port a ``scheme://[user[:pw]@]host[:port][/path][?query]`` URL names.

    A URL without a host (``postgresql:///db``) means this machine; one without a port
    gets ``default_port``. ``None`` when the string is not a URL or its port is not a number.
    """
    if "://" not in url:
        return None
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        return None
    return parts.hostname or "localhost", port or default_port


def tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def url_reachable(url: str, default_port: int, timeout: float = 1.0) -> bool:
    """True when something accepts a TCP connection at the host and port the URL names."""
    endpoint = url_host_port(url, default_port)
    return endpoint is not None and tcp_reachable(*endpoint, timeout=timeout)
