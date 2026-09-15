"""HTTP client wrapper for AITBC CLI.

Re-exports the canonical ``AITBCHTTPClient`` and ``NetworkError`` from
``aitbc.network`` (consolidated in v0.10.4).  Keeps CLI-specific
``get_logger`` and ``KEYSTORE_DIR`` for backward compatibility with
the ~50 CLI command files that import from this module.

Also hosts the shared base-URL and credential helpers the command modules
use, so the ``coordinator_api_url`` conventions stay in one place (GAP-22).
"""

from typing import Any
from urllib.parse import urlparse

from aitbc.aitbc_logging import get_logger  # noqa: F401 — re-export
from aitbc.exceptions import NetworkError  # noqa: F401 — re-export
from aitbc.network.client import AITBCHTTPClient  # noqa: F401 — re-export

# Constants
KEYSTORE_DIR = "/var/lib/aitbc/keystore"


def looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots."""
    return token.startswith("ey") and token.count(".") == 2


def service_root_url(url: str | None, default: str = "") -> str:
    """Return a service root URL without a trailing ``/`` or ``/v1``.

    Most coordinator call sites carry absolute ``/v1/...`` (or
    ``/api/v1/...``) paths themselves, so a configured
    ``coordinator_api_url`` that already ends in ``/v1`` (e.g.
    ``https://<hub>/c/v1``) must not produce doubled ``/v1/v1/...``
    paths. Mount prefixes such as ``/c`` or ``/agent`` are preserved —
    only a single trailing ``/v1`` segment is stripped.
    """
    base = (url or "").rstrip("/") or default
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def normalize_base_url(url: str | None, default: str = "") -> str:
    """Return a versioned API base URL that always ends in ``/v1``.

    The counterpart of :func:`service_root_url` for call sites that carry
    paths relative to the version root (e.g. ``/reputation/...``): a
    configured service root and an already-versioned value normalize to
    the same ``<root>/v1`` base.
    """
    return f"{service_root_url(url, default)}/v1"


def origin_base_url(url: str | None, default: str = "") -> str:
    """Reduce a URL to ``scheme://host[:port]``, dropping any path.

    For configured values that already carry a mounted API prefix — e.g.
    ``agent_coordinator_url`` resolves to ``https://<hub>/api/v1/agent`` —
    while the call sites carry absolute paths such as ``/v1/...`` or
    ``/api/v1/agent/...`` themselves, so keeping the prefix would double it.
    """
    raw = str(url or "") or default
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw.rstrip("/")


def auth_client_kwargs(
    explicit_key: str | None = None,
    config_key: str | None = None,
    *,
    credential: str = "client",
    use_store: bool = True,
) -> dict[str, Any]:
    """Return ``AITBCHTTPClient`` kwargs carrying the best available credential.

    Precedence: the explicit ``--api-key`` value, then the ``auth login``
    credential store (the named slot, falling back to ``client``, or the
    ``admin``-aware lookup when ``credential="admin"``), then the configured
    API key. A JWT-shaped token goes in ``Authorization: Bearer``; anything
    else is sent via the client's ``api_key`` kwarg (``X-API-Key``). Returns
    ``{}`` when no credential exists.
    """
    token = explicit_key
    if not token and use_store:
        from ..auth import AuthManager  # late import: auth imports ..utils

        manager = AuthManager()
        if credential == "admin":
            # May raise ExpiredAdminToken — callers surface it as a re-auth hint.
            token = manager.get_admin_token()
        else:
            token = manager.get_credential(credential, quiet=True)
            if not token and credential != "client":
                token = manager.get_credential("client", quiet=True)
    if not token:
        token = config_key
    if not token:
        return {}
    if looks_like_jwt(token):
        return {"headers": {"Authorization": f"Bearer {token}"}}
    return {"api_key": token}


def auth_headers(
    explicit_key: str | None = None,
    config_key: str | None = None,
    *,
    credential: str = "client",
    use_store: bool = True,
) -> dict[str, str]:
    """Header-dict form of :func:`auth_client_kwargs` for raw httpx/requests callers."""
    kwargs = auth_client_kwargs(explicit_key, config_key, credential=credential, use_store=use_store)
    headers = dict(kwargs.get("headers") or {})
    if kwargs.get("api_key"):
        headers["X-API-Key"] = kwargs["api_key"]
    return headers
