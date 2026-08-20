"""Resolve the public hub host from the node's env files.

Shop and follower nodes do not run ``aitbc-exchange`` or
``aitbc-agent-coordinator``. Those services live on the hub, so any default
that names ``localhost:8106`` / ``:8107`` is wrong off-hub (V23-92).

The host itself is an operator setting — ``HUB_DISCOVERY_URL`` in
``/etc/aitbc/blockchain.env`` or ``/etc/aitbc/node.env`` (node wins). Explicit
process env always wins over the files. There is no baked-in hostname: a node
that has not been told where its hub is cannot invent one.
"""

from __future__ import annotations

import os
from pathlib import Path

from aitbc.constants import CONFIG_DIR

def _env_files() -> tuple[Path, Path]:
    return (CONFIG_DIR / "blockchain.env", CONFIG_DIR / "node.env")


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def hub_discovery_host() -> str | None:
    """The hub's DNS name, or None if nothing in the environment named one.

    Precedence: process env ``HUB_DISCOVERY_URL``, then ``node.env``, then
    ``blockchain.env``. A URL is reduced to its host so callers can append a
    path without doubling schemes.
    """
    raw = os.getenv("HUB_DISCOVERY_URL")
    if not raw:
        files = {k: v for path in _env_files() for k, v in _read_env_file(path).items()}
        raw = files.get("HUB_DISCOVERY_URL")
    if not raw:
        return None
    host = raw.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    return host.split("/", 1)[0].rstrip("/") or None


def hub_service_url(path: str) -> str | None:
    """``https://<hub>/<path>`` when a hub host is configured, else None."""
    host = hub_discovery_host()
    if not host:
        return None
    return f"https://{host}/{path.lstrip('/')}"


def hub_agent_url() -> str | None:
    """Where the hub's agent API is mounted.

    ``HUB_AGENT_URL`` / ``HUB_HERMES_URL`` are already a full base (prefix
    included). Otherwise the path is built from ``HUB_DISCOVERY_URL``.
    """
    explicit = os.getenv("HUB_AGENT_URL") or os.getenv("HUB_HERMES_URL")
    if explicit:
        return explicit.rstrip("/")
    return hub_service_url("api/v1/agent")


def hub_exchange_url() -> str | None:
    """Where the hub's exchange API is mounted."""
    explicit = os.getenv("HUB_EXCHANGE_URL") or os.getenv("EXCHANGE_SERVICE_URL")
    if explicit:
        return explicit.rstrip("/")
    return hub_service_url("exchange")


def hub_coordinator_url() -> str | None:
    """Where the hub's coordinator API is mounted.

    ``HUB_COORDINATOR_URL`` / ``COORDINATOR_API_URL`` are already a full base
    (prefix included). Otherwise the path is built from ``HUB_DISCOVERY_URL``.
    """
    explicit = os.getenv("HUB_COORDINATOR_URL") or os.getenv("COORDINATOR_API_URL")
    if explicit:
        return explicit.rstrip("/")
    # The coordinator-api is mounted under /v1 in the service. Public nginx
    # can proxy it at /v1 or at a dedicated path; default to /v1.
    return hub_service_url("v1")
