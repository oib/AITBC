"""Remote health probe command.

Probes AITBC service health endpoints on a remote host without requiring raw curl.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

import click
import httpx

from ..utils import output, resolve_output_format, success, warning
from ..utils.error_handling import abort

# Default AITBC service health probes.  Port and path are relative to a plain
# hostname/IP; if the user passes a full URL it is treated as a single probe.
DEFAULT_SERVICE_PROBES: dict[str, dict[str, Any]] = {
    "api-gateway": {"port": 8201, "path": "/health"},
    "blockchain-rpc": {"port": 8202, "path": "/health"},
    "coordinator-api": {"port": 8203, "path": "/health"},
    "explorer": {"port": 8100, "path": "/health"},
    "marketplace": {"port": 8102, "path": "/health"},
    "trading": {"port": 8104, "path": "/health"},
    "governance": {"port": 8105, "path": "/health"},
    "wallet": {"port": 8108, "path": "/health"},
    "pool-hub": {"port": 8210, "path": "/health"},
    "edge": {"port": 8111, "path": "/health"},
    "gpu": {"port": 8101, "path": "/health"},
    "ffmpeg": {"port": 8230, "path": "/health"},
    "whisper": {"port": 8110, "path": "/health"},
    "hermes": {"port": 8270, "path": "/health"},
    "monitoring": {"port": 8002, "path": "/health"},
}


def _is_full_url(host: str) -> bool:
    """Return True if host already looks like a URL."""
    return host.startswith(("http://", "https://"))


def _probe_url(url: str, timeout: float) -> dict[str, Any]:
    """Probe a single URL and return a result row."""
    start = perf_counter()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
    except httpx.ConnectError as exc:
        return {
            "url": url,
            "status_code": None,
            "status": "connect_error",
            "latency_ms": round((perf_counter() - start) * 1000, 2),
            "error": str(exc),
        }
    except httpx.TimeoutException as exc:
        return {
            "url": url,
            "status_code": None,
            "status": "timeout",
            "latency_ms": round((perf_counter() - start) * 1000, 2),
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "status_code": None,
            "status": "error",
            "latency_ms": round((perf_counter() - start) * 1000, 2),
            "error": str(exc),
        }

    elapsed = round((perf_counter() - start) * 1000, 2)
    return {
        "url": url,
        "status_code": response.status_code,
        "status": "healthy" if response.status_code == 200 else "unhealthy",
        "latency_ms": elapsed,
        "error": None,
    }


@click.command(
    epilog="""Examples:

  aitbc health --host node2.aitbc.bubuit.net

  aitbc health --host 10.1.223.136 --services blockchain-rpc,edge

  aitbc health --host https://hub.aitbc.bubuit.net"""
)
@click.option("--host", "host", required=True, help="Remote host to probe (hostname, IP, or http(s):// URL).")
@click.option(
    "--services",
    default="",
    help="Comma-separated list of services to probe (default: all known AITBC services).",
)
@click.option("--timeout", type=float, default=5.0, help="Timeout per request in seconds.")
@click.option("--output", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format.")
@click.pass_context
def health(ctx: click.Context, host: str, services: str, timeout: float, output_format: str):
    """Probe AITBC service health endpoints on a remote host."""
    output_format = resolve_output_format(ctx, output_format)

    if _is_full_url(host):
        base_url = host.rstrip("/")
        urls = [f"{base_url}/health"]
        results = [_probe_url(url, timeout) for url in urls]
    else:
        host = host.rstrip("/")
        selected = [s.strip() for s in services.split(",") if s.strip()] if services else list(DEFAULT_SERVICE_PROBES)
        unknown = [s for s in selected if s not in DEFAULT_SERVICE_PROBES]
        if unknown:
            abort(ctx, f"Unknown service(s): {', '.join(unknown)}")

        results = []
        for service in selected:
            probe = DEFAULT_SERVICE_PROBES[service]
            url = f"http://{host}:{probe['port']}{probe['path']}"
            row = {"service": service, **_probe_url(url, timeout)}
            results.append(row)

    healthy = [r for r in results if r.get("status") == "healthy"]
    unhealthy = [r for r in results if r.get("status") != "healthy"]

    if unhealthy:
        warning(f"{len(unhealthy)} endpoint(s) are not healthy.")
    else:
        success(f"All {len(healthy)} probed endpoint(s) are healthy.")

    output(results, output_format, title="Remote Health")
