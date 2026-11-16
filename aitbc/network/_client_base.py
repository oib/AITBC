"""Shared transport helpers for the AITBC HTTP clients.

Extracted verbatim from ``client.py``: error-detail enrichment, response
JSON decoding inside the retry boundary, the credential-header guard
(``set_trusted_api_key_hosts`` / ``_check_api_key_target`` /
``_CredentialSafeSession``) and ``_response_json``. ``client.py`` re-exports
these names so ``aitbc.network.client.<name>`` keeps resolving.
"""

import json
from typing import Any
from urllib.parse import urlparse

import httpx
import requests

from ..aitbc_logging import get_logger
from .json_types import JSONResponse

_DETAIL_CAP = 300

logger = get_logger(__name__)


def _detail_suffix(exc: BaseException) -> str:
    """Return ``": <server detail>"`` for a wrapped HTTP error, else ``""``.

    Walks the exception chain for the first response object (``requests``
    or ``httpx``) and extracts the body's ``detail`` string (or an
    ``error.message`` envelope), capped at ``_DETAIL_CAP`` characters.
    Carrying it in the ``NetworkError`` message means every caller that
    prints ``{e}`` shows the node's refusal reason — previously the body
    survived only via ``http_error_detail`` which few call sites use.
    Response detail only; a request body is never echoed.
    """
    try:
        return _detail_suffix_inner(exc)
    except Exception as e:  # noqa: BLE001 - best-effort enrichment, never mask the wrapped error
        logger.debug("error-detail extraction failed: %s", type(e).__name__)
        return ""


def _detail_suffix_inner(exc: BaseException) -> str:
    seen: BaseException | None = exc
    while seen is not None:
        response = getattr(seen, "response", None)
        if response is not None:
            try:
                body = response.json()
            except ValueError:
                return ""
            detail: Any = None
            if isinstance(body, dict):
                detail = body.get("detail")
                if isinstance(detail, list) and detail:
                    # FastAPI 422: [{"loc": [...], "msg": "..."}, ...]
                    parts = []
                    for item in detail[:3]:
                        if isinstance(item, dict) and item.get("msg"):
                            loc = ".".join(str(p) for p in (item.get("loc") or []) if p != "body")
                            parts.append(f"{loc}: {item['msg']}" if loc else str(item["msg"]))
                    detail = "; ".join(parts) or None
                if not isinstance(detail, str) or not detail:
                    err = body.get("error")
                    detail = err.get("message") if isinstance(err, dict) else (err if isinstance(err, str) else None)
            if isinstance(detail, str) and detail:
                return f": {detail[:_DETAIL_CAP]}"
            return ""
        seen = seen.__cause__ or seen.__context__
    return ""


def _response_json(response: httpx.Response) -> JSONResponse:
    """Parse a successful response body inside the retry boundary.

    Returns ``{}`` for empty bodies (204/205). A body that is not JSON at
    all raises the stdlib ``json.JSONDecodeError`` unchanged: it is a
    ``ValueError``, not an ``httpx.HTTPError``, so the retry policy does not
    replay the request and the caller sees the parse failure directly (the
    escrow-funding lookup relies on exactly that contract). Any other
    ``ValueError`` from the decoder is translated into ``httpx.DecodingError``
    so it still picks up the GET-retry / write-ambiguity semantics of the
    retry boundary instead of leaking an unclassified error.
    """
    if not response.content:
        return {}
    try:
        parsed: JSONResponse = response.json()
    except json.JSONDecodeError:
        raise
    except ValueError as e:
        try:
            request = response.request
        except RuntimeError:
            request = None
        raise httpx.DecodingError(str(e), request=request) from e
    return parsed


# Hosts a configured API key may be sent to. The CLI registers its
# configured service URLs here at config load (#850); ``None`` means no
# restriction — service processes that never register behave exactly as
# before. A caller-supplied URL to a foreign host then cannot carry the
# node's stored credential to whoever controls it.
_trusted_api_key_hosts: frozenset[str] | None = None

# Header names that carry a credential. The guard must cover every one of
# them, not just the ``api_key`` kwarg: ``auth_client_kwargs`` emits JWTs
# as ``Authorization: Bearer`` and the trading path uses
# ``X-Trading-Api-Key`` — checking only ``api_key`` let those ride to any
# host (PI-SDK-01). ``x-settlement-key`` is the escrow release/refund
# settlement credential (#1917) — same exposure rules.
_CREDENTIAL_HEADER_NAMES = frozenset({"authorization", "x-api-key", "x-trading-api-key", "x-settlement-key"})


def set_trusted_api_key_hosts(hosts: frozenset[str] | None) -> None:
    global _trusted_api_key_hosts
    _trusted_api_key_hosts = hosts


def _has_credential_headers(headers: dict[str, str]) -> bool:
    return any(str(name).lower() in _CREDENTIAL_HEADER_NAMES for name in headers)


def _strip_credential_headers(headers: dict[str, str]) -> None:
    for name in list(headers):
        if str(name).lower() in _CREDENTIAL_HEADER_NAMES:
            del headers[name]


class _CredentialSafeSession(requests.Session):
    """Session that drops credential headers when a redirect leaves the origin.

    ``requests`` strips ``Authorization`` on cross-host redirects but replays
    every other header verbatim — a 30x from a trusted host would forward
    ``X-API-Key``/``X-Trading-Api-Key`` to whoever the ``Location`` names
    (#1577). ``rebuild_auth`` runs once per redirect hop before the follow-up
    request is sent, so removing the headers here is the last point where the
    leak can still be stopped. Same-host redirects (and https→https port
    changes) keep the credentials.
    """

    def rebuild_auth(self, prepared_request, response):
        super().rebuild_auth(prepared_request, response)
        old = urlparse(response.url)
        new = urlparse(prepared_request.url)
        old_host = (old.hostname or "").lower()
        new_host = (new.hostname or "").lower()
        old_scheme = (old.scheme or "").lower()
        new_scheme = (new.scheme or "").lower()
        if old_host != new_host or old_scheme != new_scheme:
            _strip_credential_headers(prepared_request.headers)


def _check_api_key_target(base_url: str, api_key: str | None = None, headers: dict[str, str] | None = None) -> None:
    if _trusted_api_key_hosts is None:
        return
    if not api_key and not _has_credential_headers(headers or {}):
        return
    host = urlparse(base_url).hostname or ""
    if host not in _trusted_api_key_hosts:
        raise ValueError(
            f"refusing to send the configured credential to unconfigured host {host!r} "
            f"(url {base_url!r}); add the service URL to the CLI config to trust it"
        )
