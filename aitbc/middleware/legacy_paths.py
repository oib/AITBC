"""Legacy URL-prefix compatibility for the marketplace → market rename.

The rename moved every public route from ``/v1/marketplace/*`` to
``/v1/market/*`` (and ``/rpc/marketplace/*`` to ``/rpc/market/*`` on the chain
node). The compatibility aliases the rename promised were never implemented, so
a caller still pinned to the old spelling got no useful signal: on the
coordinator the auth layer runs ahead of routing, which turns an unknown path
into 401/403 — indistinguishable from a real permission denial, never a 404.

Rewriting the prefix in the ASGI scope, ahead of every other middleware, covers
each route under it with one declaration and keeps auth, rate limiting and
logging looking at the canonical path. Responses carry the legacy path back in
``X-AITBC-Deprecated-Path`` so the remaining callers can be found and retired.
"""

from __future__ import annotations

from collections.abc import Mapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

#: Legacy prefix → canonical prefix. Services that mount the RPC router under
#: ``/rpc`` get both; the ``/v1`` entry alone is right for everyone else.
MARKETPLACE_PATH_ALIASES: Mapping[str, str] = {
    "/v1/marketplace": "/v1/market",
    "/rpc/marketplace": "/rpc/market",
}

DEPRECATION_HEADER = "X-AITBC-Deprecated-Path"

# Cap on the distinct legacy paths remembered for log de-duplication. A caller
# hammering one dead route should warn once, not once per request; a caller
# inventing unbounded paths must not grow this set without limit.
_SEEN_PATH_LIMIT = 256


class LegacyPathRewriteMiddleware:
    """Rewrite legacy URL prefixes to their canonical spelling before routing.

    Plain ASGI rather than ``BaseHTTPMiddleware``: the chain node serves
    websockets on the same app, and ``BaseHTTPMiddleware`` only sees ``http``
    scopes, so the alias would silently not apply to them.
    """

    def __init__(self, app: ASGIApp, aliases: Mapping[str, str] | None = None) -> None:
        self.app = app
        source = MARKETPLACE_PATH_ALIASES if aliases is None else aliases
        # Longest legacy prefix first, so an alias is never shadowed by a
        # shorter one that happens to be its prefix.
        self._aliases: tuple[tuple[str, str], ...] = tuple(
            sorted(
                ((old.rstrip("/"), new.rstrip("/")) for old, new in source.items()),
                key=lambda pair: -len(pair[0]),
            )
        )
        self._seen: set[str] = set()

    def _match(self, path: str) -> tuple[str, str] | None:
        """Return the (legacy, canonical) prefix pair covering ``path``."""
        for old, new in self._aliases:
            # An exact hit or a path segment boundary only: "/v1/marketplaces"
            # is a different route family, not a legacy spelling.
            if path == old or path.startswith(old + "/"):
                return old, new
        return None

    def _log(self, original: str, canonical: str) -> None:
        if original in self._seen:
            logger.debug("Legacy path %s → %s", original, canonical)
            return
        if len(self._seen) < _SEEN_PATH_LIMIT:
            self._seen.add(original)
        logger.warning(
            "Legacy path %s served through the compatibility alias for %s; update the caller",
            original,
            canonical,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        original = scope.get("path", "")
        match = self._match(original)
        if match is None:
            await self.app(scope, receive, send)
            return

        old, new = match
        canonical = new + original[len(old) :]
        self._log(original, canonical)

        scope = dict(scope)
        scope["path"] = canonical
        raw_path = scope.get("raw_path")
        if isinstance(raw_path, bytes):
            # Both prefixes are ASCII and never percent-encoded in practice, so
            # swapping the prefix leaves the encoded remainder untouched.
            old_raw = old.encode("ascii")
            if raw_path.startswith(old_raw):
                scope["raw_path"] = new.encode("ascii") + raw_path[len(old_raw) :]

        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        async def send_with_deprecation(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [
                    *message.get("headers", []),
                    (DEPRECATION_HEADER.lower().encode("ascii"), original.encode("latin-1")),
                ]
            await send(message)

        await self.app(scope, receive, send_with_deprecation)
