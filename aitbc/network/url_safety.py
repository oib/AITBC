"""SSRF guard for operator- or user-registered outbound URLs.

Webhook/callback stores (partner webhooks, alerting webhooks) accept URLs
from callers or config and later POST to them. Before a dispatcher exists —
and again at send time — the URL must be proven to target a public host:
http(s) scheme only, and every address the host resolves to must be a
global unicast address. Loopback, private, link-local (incl. the cloud
metadata address 169.254.169.254), multicast and reserved ranges are all
refused.

Escape hatch: comma-separated ``host[:port]`` entries in an env var let an
operator whitelist internal targets (same pattern as
``MARKET_HEALTH_ALLOWED_TARGETS``). Callers pass their own env var name so
each store keeps an independent allowlist.

Note the DNS-rebinding caveat: this check runs at registration/config time.
A delivery worker MUST re-run it (or pin the resolved address) immediately
before each POST — a hostname can resolve differently later.
"""

import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlparse

_SCHEMES = ("http", "https")


def _parse(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _SCHEMES:
        raise ValueError(f"scheme not allowed: {parsed.scheme or '(none)'}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("no host")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as e:
        raise ValueError(f"invalid port in url: {url!r}") from e
    return scheme, host, port


def _allowlist(env_var: str) -> set[str]:
    return {t.strip().lower() for t in os.environ.get(env_var, "").split(",") if t.strip()}


def _check_resolved(host: str, port: int, addrs: list[str]) -> None:
    if not addrs:
        raise ValueError(f"host does not resolve: {host}")
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if not ip.is_global:
            raise ValueError(f"{host} resolves to a non-public address: {ip}")


def validate_outbound_url(url: str, *, allowlist_env: str = "AITBC_OUTBOUND_URL_ALLOWED_TARGETS") -> None:
    """Raise ValueError unless *url* is http(s) targeting a public host.

    ``allowlist_env`` names the env var holding comma-separated ``host[:port]``
    entries exempt from the public-address requirement.
    """
    _, host, port = _parse(url)
    allowed = _allowlist(allowlist_env)
    if host.lower() in allowed or f"{host.lower()}:{port}" in allowed:
        return
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"host does not resolve: {host}") from e
    _check_resolved(host, port, [str(info[4][0]) for info in infos])


async def avalidate_outbound_url(url: str, *, allowlist_env: str = "AITBC_OUTBOUND_URL_ALLOWED_TARGETS") -> None:
    """Async variant of :func:`validate_outbound_url` (non-blocking DNS)."""
    _, host, port = _parse(url)
    allowed = _allowlist(allowlist_env)
    if host.lower() in allowed or f"{host.lower()}:{port}" in allowed:
        return
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"host does not resolve: {host}") from e
    _check_resolved(host, port, [str(info[4][0]) for info in infos])


def _address_is_fleet_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for address classes a fleet outbound URL must never target.

    Mirrors ``_address_is_forbidden`` in the blockchain sync peer check:
    private and global addresses are allowed (fleet services legitimately
    live on private LANs); loopback, link-local (incl. cloud metadata
    169.254.169.254), multicast, reserved and unspecified are refused.
    IPv4-mapped IPv6 is checked as its embedded IPv4 address.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return bool(ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _check_resolved_fleet(host: str, port: int, addrs: list[str]) -> None:
    if not addrs:
        raise ValueError(f"host does not resolve: {host}")
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if _address_is_fleet_forbidden(ip):
            raise ValueError(f"{host} resolves to a forbidden address: {ip}")


def _parse_base_url(url: str) -> tuple[str, str, int]:
    """Like :func:`_parse` but also rejects query/fragment/userinfo.

    Fleet service endpoints are stored as base URLs and later concatenated
    with paths (``f"{endpoint}/tasks/execute"``) — a ``?`` or ``#`` in the
    stored value would silently rewrite the effective request target.
    """
    scheme, host, port = _parse(url)
    parsed = urlparse(url)
    if parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
        raise ValueError(f"base URL must not contain query, fragment or userinfo: {url!r}")
    return scheme, host, port


def _resolve_fleet(url: str, *, allowlist_env: str) -> list[str]:
    _, host, port = _parse_base_url(url)
    allowed = _allowlist(allowlist_env)
    if host.lower() in allowed or f"{host.lower()}:{port}" in allowed:
        return []
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"host does not resolve: {host}") from e
    return [str(info[4][0]) for info in infos]


async def _aresolve_fleet(url: str, *, allowlist_env: str) -> list[str]:
    _, host, port = _parse_base_url(url)
    allowed = _allowlist(allowlist_env)
    if host.lower() in allowed or f"{host.lower()}:{port}" in allowed:
        return []
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"host does not resolve: {host}") from e
    return [str(info[4][0]) for info in infos]


def validate_fleet_outbound_url(url: str, *, allowlist_env: str = "AITBC_OUTBOUND_URL_ALLOWED_TARGETS") -> None:
    """Raise ValueError unless *url* is an http(s) base URL safe for fleet use.

    Unlike :func:`validate_outbound_url` (public-only, for partner webhooks),
    this permits private LAN addresses — fleet peers and services live on
    RFC-1918 ranges — while still refusing loopback, link-local/cloud
    metadata, multicast, reserved and unspecified targets. Query strings,
    fragments and userinfo are rejected because callers concatenate paths
    onto the stored value.
    """
    addrs = _resolve_fleet(url, allowlist_env=allowlist_env)
    if addrs:
        _, host, port = _parse_base_url(url)
        _check_resolved_fleet(host, port, addrs)


async def avalidate_fleet_outbound_url(url: str, *, allowlist_env: str = "AITBC_OUTBOUND_URL_ALLOWED_TARGETS") -> None:
    """Async variant of :func:`validate_fleet_outbound_url` (non-blocking DNS)."""
    addrs = await _aresolve_fleet(url, allowlist_env=allowlist_env)
    if addrs:
        _, host, port = _parse_base_url(url)
        _check_resolved_fleet(host, port, addrs)
