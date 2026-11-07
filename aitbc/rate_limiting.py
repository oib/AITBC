"""
Rate limiting utilities for FastAPI applications
Provides decorators and middleware for API rate limiting
"""

import asyncio
import ipaddress
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import wraps
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .aitbc_logging import get_logger
from .security import RateLimiter
from .utils.env import is_production

logger = get_logger(__name__)
_rate_limiters: dict[str, RateLimiter] = {}


def _is_rate_limiting_enabled() -> bool:
    """Return whether rate limiting should be enforced.

    Production environments cannot disable rate limiting. Non-production
    environments may set ``AITBC_ENABLE_RATE_LIMITING=false`` to bypass it.
    """
    if is_production():
        return True
    return os.getenv("AITBC_ENABLE_RATE_LIMITING", "true").lower() not in ("false", "0", "no", "off")


def get_rate_limiter(name: str, rate: int = 100, per: int = 60) -> RateLimiter:
    """
    Get or create a rate limiter for a specific endpoint

    Args:
        name: Unique name for the rate limiter
        rate: Number of requests allowed per time period
        per: Time period in seconds

    Returns:
        RateLimiter instance
    """
    if name not in _rate_limiters:
        _rate_limiters[name] = RateLimiter(rate=rate, per=per)
    return _rate_limiters[name]


def _extract_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    """Find the FastAPI Request object in the handler's positional or keyword args."""
    for arg in args:
        if isinstance(arg, Request):
            return arg
    for arg in kwargs.values():
        if isinstance(arg, Request):
            return arg
    return None


_warned_unkeyed: set[str] = set()


_DEFAULT_TRUSTED_PROXIES = "127.0.0.1,::1"
_trusted_cache: tuple[str, tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] | None = None


def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Networks whose forwarding headers we believe (``AITBC_TRUSTED_PROXIES``).

    Comma-separated IPs or CIDRs, default loopback: the nginx and gateway
    hops on a node. Same trust contract as the exchange's
    ``EXCHANGE_TRUSTED_PROXIES``. Re-parsed only when the variable changes.
    """
    global _trusted_cache
    raw = os.getenv("AITBC_TRUSTED_PROXIES", _DEFAULT_TRUSTED_PROXIES)
    if _trusted_cache is not None and _trusted_cache[0] == raw:
        return _trusted_cache[1]
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.warning("AITBC_TRUSTED_PROXIES: ignoring unparseable entry %r", part)
    _trusted_cache = (raw, tuple(nets))
    return _trusted_cache[1]


def _is_trusted_proxy(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    # A dual-stack listener reports an IPv4 peer as ::ffff:a.b.c.d.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return any(addr in net for net in _trusted_proxy_networks())


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip_from_peer_and_headers(peer: str | None, headers: Mapping[str, str]) -> str:
    """Return the client IP to key a rate limit on, from a peer and headers.

    The TCP peer is the only value a client cannot choose, so it is the key
    unless the peer is itself a trusted proxy (``AITBC_TRUSTED_PROXIES``,
    default loopback). Only then are the forwarding headers read: first
    ``X-Real-IP`` (nginx overwrites it with ``$remote_addr``; the gateway
    does the same), then the right-most ``X-Forwarded-For`` entry that is not
    a trusted proxy. Entries to the left of that are whatever the client sent
    and never count. Behind uvicorn ``--proxy-headers`` the peer has already
    been rewritten to the real client, which is untrusted, so the headers are
    skipped and the rewritten peer wins.

    Before #1244 any client could write ``X-Real-IP`` / ``X-Forwarded-For``
    and mint a fresh bucket per request. ``headers`` must be case-insensitive
    (Starlette ``Headers`` is). Shared by HTTP requests and the gossip
    websocket (#1241), which has no ``Request`` object.
    """
    if not peer:
        return "unknown"
    if not _is_trusted_proxy(peer):
        return peer

    real = _valid_ip(headers.get("x-real-ip", "").split(",")[0])
    if real:
        return real

    for hop in reversed(headers.get("x-forwarded-for", "").split(",")):
        candidate = _valid_ip(hop)
        if candidate and not _is_trusted_proxy(candidate):
            return candidate
    return peer


def _client_ip_for_rate_limit(request: Request) -> str:
    """Request-shaped wrapper over :func:`client_ip_from_peer_and_headers`."""
    return client_ip_from_peer_and_headers(request.client.host if request.client else "", request.headers)


def client_ip_for_rate_limit(request: Request) -> str:
    """Public wrapper for manual rate-limit sites (e.g. cooldown dicts) so
    they key on the same proxied client IP as the ``rate_limit`` decorator
    instead of the immediate peer."""
    return _client_ip_for_rate_limit(request)


def _get_rate_limit_key(request: Request | None, key_func: Callable[[Request], str] | None, handler: str = "?") -> str:
    """Extract the rate limit key from the request.

    A handler that does not declare a ``request: Request`` parameter gives us nothing to key
    on, and every caller then shares the single ``"unknown"`` bucket — so one client
    exhausting the limit locks out everyone, which is a denial of service handed out by the
    protection. That is silent otherwise, so warn once per handler.
    """
    if request is None:
        if handler not in _warned_unkeyed:
            _warned_unkeyed.add(handler)
            logger.warning(
                "Rate limit on %s cannot identify the caller: the handler has no 'request: Request' "
                "parameter, so all callers share one bucket and any one of them can lock out the "
                "rest. Add the parameter, or pass an explicit key_func.",
                handler,
            )
        return "unknown"
    if key_func:
        return key_func(request)
    return _client_ip_for_rate_limit(request)


def rate_limit(
    rate: int = 100,
    per: int = 60,
    key_func: Callable[[Request], str] | None = None,
    error_message: str = "Rate limit exceeded",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for rate limiting FastAPI endpoints.

    Uses a token-bucket algorithm via the RateLimiter class. Rate limiting is
    enabled by default and cannot be disabled in production.
    """
    from typing import ParamSpec

    P = ParamSpec("P")

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        limiter_name = f"rl_{rate}_{per}_{id(key_func)}_{func.__name__}"
        _limiter = get_rate_limiter(limiter_name, rate=rate, per=per)
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                if not _is_rate_limiting_enabled():
                    logger.debug("Rate limiting bypassed for %s", func.__name__)
                    return await func(*args, **kwargs)

                request = _extract_request(args, kwargs)
                key = _get_rate_limit_key(request, key_func, func.__qualname__)
                if not _limiter.is_allowed(key):
                    logger.warning("Rate limit exceeded for %s on %s", key, request.url.path if request else "?", stacklevel=2)
                    raise HTTPException(
                        status_code=429,
                        detail=error_message,
                        headers={"Retry-After": str(per)},
                    )
                return await func(*args, **kwargs)

            return wrapper
        else:

            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                if not _is_rate_limiting_enabled():
                    logger.debug("Rate limiting bypassed for %s", func.__name__)
                    return func(*args, **kwargs)

                request = _extract_request(args, kwargs)
                key = _get_rate_limit_key(request, key_func, func.__qualname__)
                if not _limiter.is_allowed(key):
                    logger.warning("Rate limit exceeded for %s on %s", key, request.url.path if request else "?", stacklevel=2)
                    raise HTTPException(
                        status_code=429,
                        detail=error_message,
                        headers={"Retry-After": str(per)},
                    )
                return func(*args, **kwargs)

            return wrapper

    return decorator


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware for rate limiting all requests

    Applies rate limiting based on client IP address
    """

    def __init__(
        self,
        app: ASGIApp,
        rate: int = 100,
        per: int = 60,
        key_func: Callable[[Request], str] | None = None,
        error_message: str = "Rate limit exceeded",
        exclude_paths: Sequence[str] | None = None,
    ) -> None:
        """
        Initialize rate limit middleware

        Args:
            app: ASGI application
            rate: Number of requests allowed per time period
            per: Time period in seconds
            key_func: Function to extract rate limit key from request
            error_message: Custom error message
            exclude_paths: Exact paths that bypass the limit. Liveness, readiness and
                metrics endpoints belong here: probes and scrapers poll on a fixed
                interval from a fixed address, so counting them against a per-IP budget
                means the orchestrator can exhaust it and then read the resulting 429 as
                the service being unhealthy.

        Note:
            The limiter is in-process. Behind N workers the effective limit is N x rate,
            because each worker keeps its own counts. That is a ceiling on abuse, not an
            exact quota; a precise one needs shared state.
        """
        super().__init__(app)
        self.rate = rate
        self.per = per
        self.key_func = key_func
        self.error_message = error_message
        self.exclude_paths = frozenset(exclude_paths or ())
        self._limiter = RateLimiter(rate=rate, per=per)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """
        Process request with rate limiting

        Args:
            request: Incoming request
            call_next: Next middleware or endpoint

        Returns:
            Response
        """
        # The decorator consulted this and the middleware did not, so AITBC_ENABLE_RATE_LIMITING
        # worked or was ignored depending on which mechanism a service happened to use. Both
        # honour it now, and neither can be disabled in production.
        if not _is_rate_limiting_enabled():
            return await call_next(request)

        if request.url.path in self.exclude_paths:
            return await call_next(request)

        key = self.key_func(request) if self.key_func else request.client.host if request.client else "unknown"
        if not self._limiter.is_allowed(key):
            logger.warning("Rate limit exceeded for %s on %s", key, request.url.path, stacklevel=2)
            # JSONResponse rather than hand-built JSON: error_message is caller-supplied, and
            # an f-string into a JSON literal produces malformed output the moment it
            # contains a quote or a backslash.
            return JSONResponse(
                content={"detail": self.error_message},
                status_code=429,
                headers={"Retry-After": str(self.per)},
            )
        response = await call_next(request)
        return response


def get_rate_limit_headers(request: Request, limiter_name: str) -> dict[str, str]:
    """
    Get rate limit headers for response

    Args:
        request: Request object
        limiter_name: Name of the rate limiter

    Returns:
        Dictionary of rate limit headers
    """
    limiter = _rate_limiters.get(limiter_name)
    if not limiter:
        return {}
    key = request.client.host if request.client else "unknown"
    remaining = limiter.get_remaining(key)
    return {
        "X-RateLimit-Limit": str(limiter.rate),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(limiter.per),
    }


def reset_rate_limit(identifier: str, limiter_name: str | None = None) -> None:
    """
    Reset rate limit for an identifier

    Args:
        identifier: Identifier to reset (e.g., IP address, user ID)
        limiter_name: Name of specific rate limiter, or None for all
    """
    if limiter_name:
        if limiter_name in _rate_limiters:
            _rate_limiters[limiter_name].reset(identifier)
    else:
        for limiter in _rate_limiters.values():
            limiter.reset(identifier)
