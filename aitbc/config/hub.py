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


def _raw_env_value(*keys: str) -> str | None:
    """First explicit process env value, then the same key from env files."""
    files = None
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
        if files is None:
            files = {k2: v2 for path in _env_files() for k2, v2 in _read_env_file(path).items()}
        if k in files:
            return files[k]
    return None


# Where hub-ward URLs resolve on the hub itself when nothing overrides it.
# The public name hairpin-fails there (TLS terminates at the edge, which the
# hub cannot reach on its own address), while local nginx on :80 mounts the
# exact same paths. ``HUB_LOCAL_URL`` overrides the default for deployments
# whose local gateway binds elsewhere.
LOCAL_HUB_ORIGIN = "http://127.0.0.1"


def _host_from(raw: str | None) -> str | None:
    """Reduce a URL or bare hostname to a DNS host, stripping scheme and path."""
    if not raw:
        return None
    host = raw.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    return host.split("/", 1)[0].rstrip("/") or None


def _origin_from(raw: str | None) -> tuple[str, str] | None:
    """Reduce a URL or bare hostname to ``(scheme, host[:port])``.

    An explicit ``http://`` or ``https://`` prefix is honored verbatim —
    https is only the default for bare hosts, where TLS lives at the hub's
    fronting edge.
    """
    if not raw:
        return None
    value = raw.strip()
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            host = value[len(prefix) :].split("/", 1)[0].rstrip("/")
            return (prefix[: -len("://")], host) if host else None
    host = value.split("/", 1)[0].rstrip("/")
    return ("https", host) if host else None


def _hub_raw() -> str | None:
    return _raw_env_value("HUB_DISCOVERY_URL", "HUB_P2P_HOST", "HUB_RPC_URL")


def hub_discovery_host() -> str | None:
    """The hub's DNS name, or None if nothing in the environment named one.

    Precedence: process env ``HUB_DISCOVERY_URL`` falls back to ``HUB_P2P_HOST``
    and ``HUB_RPC_URL`` (already configured on follower/shop nodes).  The first
    source found is reduced to a host so callers can append paths without
    doubling schemes.
    """
    return _host_from(_hub_raw())


def is_hub_self() -> bool:
    """True when this node is the hub itself.

    Two independent signals, either sufficient:

    - ``BLOCKCHAIN_MODE=hub`` (process env or the env files — ``setup.sh``
      writes it for own-island deployments);
    - the node's identity (``NODE_ID``, ``AITBC_HOSTNAME`` or ``P2P_NODE_ID``)
      equals the configured hub host.

    The hub cannot reach its own public name — the edge does not hairpin —
    so hub-ward URLs must resolve locally when this is True.
    """
    mode = _raw_env_value("BLOCKCHAIN_MODE")
    if mode and mode.strip().lower() == "hub":
        return True
    hub_host = hub_discovery_host()
    if not hub_host:
        return False
    identity = _host_from(_raw_env_value("NODE_ID", "AITBC_HOSTNAME", "P2P_NODE_ID"))
    if not identity:
        return False
    return identity.lower() == hub_host.lower()


def _local_hub_origin() -> str:
    """Where "the hub" lives when this node is the hub.

    ``HUB_LOCAL_URL`` (process env or env files) wins; the default is local
    nginx on :80, which mounts the same paths the public edge serves.
    """
    explicit = _raw_env_value("HUB_LOCAL_URL")
    if explicit:
        return explicit.rstrip("/")
    return LOCAL_HUB_ORIGIN


def normalize_hub_base(raw: str | None) -> str | None:
    """Normalize a hub URL or bare host into a usable base origin.

    - When this node *is* the hub and ``raw`` names it, the result is the
      local origin (``HUB_LOCAL_URL`` or :data:`LOCAL_HUB_ORIGIN`) — the
      public name hairpin-fails here.
    - An explicit ``http://``/``https://`` scheme wins verbatim.
    - A localhost host gets ``http://``; any other bare host ``https://``
      (TLS terminates at the hub's fronting edge).
    """
    host = _host_from(raw)
    discovery = hub_discovery_host()
    if host is not None and discovery is not None and host.lower() == discovery.lower() and is_hub_self():
        return _local_hub_origin()
    origin = _origin_from(raw)
    if not origin:
        return None
    scheme, host = origin
    if "localhost" in host or "127.0.0.1" in host:
        scheme = "http"
    return f"{scheme}://{host}"


def hub_origin() -> str | None:
    """The hub's base origin, or None when no hub host is configured.

    Resolves the configured discovery value through
    :func:`normalize_hub_base` — ``https://<hub>`` for followers, the local
    nginx on the hub itself.
    """
    return normalize_hub_base(_hub_raw())


def hub_service_url(path: str) -> str | None:
    """``<hub-origin>/<path>`` when a hub host is configured, else None."""
    origin = hub_origin()
    if not origin:
        return None
    return f"{origin}/{path.lstrip('/')}"


def hub_agent_url() -> str | None:
    """Where the hub's agent API is mounted.

    ``HUB_AGENT_URL`` is already a full base (prefix included). Otherwise the
    path is built from ``HUB_DISCOVERY_URL``. The mount is ``/agent``: nginx
    serves the whole coordinator surface under it — ``/agent/v1/`` (registry),
    ``/agent/api/v1/agent/`` (legacy doubled paths), and ``/agent/<resource>/``
    short aliases — so every call-site convention resolves, whether it appends
    the full internal path, ``/v1/...``, or a short ``/messages/send``-style
    path. The previous default (``/api/v1/agent``) only worked for the last of
    those and produced ``/api/v1/agent/api/v1/agent/...`` for the rest.
    ``HUB_HERMES_URL`` is no longer consulted: it names the Hermes runner
    service (``/api/v1/hermes``), not the agent-coordinator.
    """
    explicit = os.getenv("HUB_AGENT_URL")
    if explicit:
        return explicit.rstrip("/")
    return hub_service_url("agent")


def hub_exchange_url() -> str | None:
    """Where the hub's exchange API is mounted.

    The signed-order routes are published at their natural ``/api/*`` paths on
    the hub host itself (OPS-4) — ``/exchange/`` is the wallet service's mount,
    not the exchange. The default base is therefore the bare hub origin.
    ``HUB_EXCHANGE_URL`` / ``EXCHANGE_SERVICE_URL`` are already full bases and
    still win.
    """
    explicit = os.getenv("HUB_EXCHANGE_URL") or os.getenv("EXCHANGE_SERVICE_URL")
    if explicit:
        return explicit.rstrip("/")
    return hub_origin()


def hub_coordinator_url() -> str | None:
    """Where the hub's coordinator API is mounted.

    ``HUB_COORDINATOR_URL`` / ``COORDINATOR_API_URL`` are already a full base
    (prefix included). Otherwise the path is built from ``HUB_DISCOVERY_URL``.
    """
    explicit = os.getenv("HUB_COORDINATOR_URL") or os.getenv("COORDINATOR_API_URL")
    if explicit:
        return explicit.rstrip("/")
    # The coordinator-api mounts its routers under /v1, but public nginx only
    # proxies the service at /c/v1 — a bare /v1 hits the API gateway, so
    # POST /v1/auth/nonce 404s there (GAP-18).
    return hub_service_url("c/v1")
