"""
HTTP client implementations for AITBC applications

The implementation is split across sibling modules: ``_client_base`` holds the
shared transport helpers (error-detail enrichment, response decoding, the
credential-target guard and ``_CredentialSafeSession``), ``_client_sync``
holds ``AITBCHTTPClient`` (requests-backed) and ``_client_async`` holds
``AsyncAITBCHTTPClient`` (httpx-backed). This module re-exports the public
client surface; ``__getattr__`` resolves every other previously-importable
name (helpers, collaborators, exception names) against the sibling modules so
``aitbc.network.client.<name>`` keeps resolving exactly as it did when the
package was a single module.
"""

from typing import Any

from ..exceptions import CircuitBreakerOpenError, NetworkError, RateLimitError, RetryError  # noqa: F401
from ._client_async import AsyncAITBCHTTPClient
from ._client_base import (
    _CREDENTIAL_HEADER_NAMES as _CREDENTIAL_HEADER_NAMES,
    _CredentialSafeSession as _CredentialSafeSession,
    _DETAIL_CAP as _DETAIL_CAP,
    _check_api_key_target as _check_api_key_target,
    _detail_suffix as _detail_suffix,
    _detail_suffix_inner as _detail_suffix_inner,
    _has_credential_headers as _has_credential_headers,
    _response_json as _response_json,
    _strip_credential_headers as _strip_credential_headers,
    set_trusted_api_key_hosts,
)
from ._client_sync import AITBCHTTPClient

__all__ = [
    "AITBCHTTPClient",
    "AsyncAITBCHTTPClient",
    "CircuitBreakerOpenError",
    "NetworkError",
    "RateLimitError",
    "RetryError",
    "set_trusted_api_key_hosts",
]


def __getattr__(name: str) -> Any:
    """Delegate names that now live in the sibling modules.

    ``_trusted_api_key_hosts`` is rebound by ``set_trusted_api_key_hosts``;
    resolving it (and every other moved name not re-exported above) through
    the owning module at access time keeps reads live — a plain
    ``from ._client_base import …`` would freeze the value at import time and
    go stale (tests read ``aitbc.network.client._trusted_api_key_hosts``
    after registering hosts).
    """
    from . import _client_async, _client_base, _client_sync

    for module in (_client_base, _client_sync, _client_async):
        try:
            return getattr(module, name)
        except AttributeError:
            continue
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
