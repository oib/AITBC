"""Regression pins for the nginx allowlist class (#1203).

Static assertions on the repo-carried reference config
(``examples/nginx/nginx-aitbc.conf.example``). These pin the security
properties fixed under #1200 (``/exchange/`` wallet-route scope),
#1202 (``/v1/bridge/`` scoping) and the realip trust structure that
#1193 hardened host-side — a revert of any of them fails here instead of
silently re-exposing the surface.

Host-managed configs (live hub vhost, ns2 edge realip) are covered by
the live-probe tier, not this file — see the #1196 suite-layout proposal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
NGINX_EXAMPLE = REPO_ROOT / "examples" / "nginx" / "nginx-aitbc.conf.example"


@pytest.fixture(scope="module")
def nginx_conf() -> str:
    assert NGINX_EXAMPLE.exists(), f"missing reference config: {NGINX_EXAMPLE}"
    return NGINX_EXAMPLE.read_text()


def _location_blocks(conf: str) -> list[str]:
    """Return each ``location ... { ... }`` block body (non-greedy)."""
    return re.findall(r"location\s+[^\n{]+\{(.*?)\n    \}", conf, re.DOTALL)


# ── #1200: /exchange/ must not blanket-proxy the whole wallet app ──────


def test_no_blanket_exchange_prefix_location(nginx_conf: str) -> None:
    """``location /exchange/ { proxy_pass http://wallet_service/; }`` exposed
    /v1/wallets admin CRUD, /v1/rpc JSON-RPC and receipts publicly
    (R10-WALLET-EXPOSE-1). Only scoped regex locations may remain."""
    assert not re.search(r"location\s+/exchange/\s*\{", nginx_conf), (
        "blanket prefix location /exchange/ reintroduced — wallet admin surface would be public again (#1200)"
    )
    # The dangerous strip-prefix proxy_pass must not appear anywhere.
    assert "proxy_pass http://wallet_service/;" not in nginx_conf


def test_exchange_scoped_public_regex_present(nginx_conf: str) -> None:
    assert re.search(r"location\s+~\s+\^/exchange/v1/\(exchange\|bridge\|receipts\)", nginx_conf), (
        "public /exchange/ scope regex missing — legit exchange-facing wallet routes would 404"
    )


def _block_after(conf: str, location_re: str, span: int = 1200) -> str:
    """Return the text following a location header match (bounded span)."""
    m = re.search(location_re, conf)
    assert m, f"location matching {location_re!r} not found"
    return conf[m.start() : m.start() + span]


def test_exchange_admin_verify_complete_loopback_only(nginx_conf: str) -> None:
    body = _block_after(nginx_conf, r"location ~ \^/exchange/v1/exchange/deposits/\[\^/\]\+/\(verify\|complete\)/\?\$ \{")
    assert "deny all;" in body and "allow 127.0.0.1;" in body


# ── #1202: /v1/bridge/ must not blanket-proxy without scoping ──────────


def test_no_blanket_bridge_prefix_location(nginx_conf: str) -> None:
    """``location /v1/bridge/`` as a plain prefix proxied every bridge route
    publicly with no per-route review (R10-BRIDGE-EXPOSE-1)."""
    assert not re.search(r"location\s+/v1/bridge/\s*\{", nginx_conf), (
        "blanket prefix location /v1/bridge/ reintroduced (#1202)"
    )


def test_bridge_ops_admin_routes_loopback_only(nginx_conf: str) -> None:
    match = re.search(
        r"location\s+~\s+\^/v1/bridge/\(poll\|polling\)\(/\|\$\)\s*\{(.*?)\n    \}",
        nginx_conf,
        re.DOTALL,
    )
    assert match, "ops-only /v1/bridge/(poll|polling) loopback block missing (#1202)"
    body = match.group(1)
    assert "deny all;" in body and "allow 127.0.0.1;" in body


def test_bridge_public_regex_present(nginx_conf: str) -> None:
    assert re.search(r"location\s+~\s+\^/v1/bridge/\s*\{", nginx_conf), "public /v1/bridge/ catch-all regex missing (#1202)"


def test_bridge_enumerable_lists_still_loopback(nginx_conf: str) -> None:
    """The /deposits|/withdrawals index regex predates #1202 — pin it so a
    refactor cannot silently re-enumerate bridge records."""
    body = _block_after(nginx_conf, r"location ~ \^/v1/bridge/\(deposits\|withdrawals\)/\?\$ \{")
    assert "deny all;" in body


# ── wallet admin prefix stays loopback-only (pre-existing, pin it) ─────


def test_v1_wallets_prefix_loopback_only(nginx_conf: str) -> None:
    match = re.search(r"location\s+/v1/wallets\s*\{(.*?)\n    \}", nginx_conf, re.DOTALL)
    assert match, "/v1/wallets location missing"
    body = match.group(1)
    assert "deny all;" in body and "allow 127.0.0.1;" in body


# ── escrow mutation allowlist (same defect class, pin it) ─────────────


def test_escrow_mutations_ip_allowlisted(nginx_conf: str) -> None:
    match = re.search(r"location\s+/rpc/escrow/\s*\{(.*?)\n    \}", nginx_conf, re.DOTALL)
    assert match, "/rpc/escrow/ location missing"
    body = match.group(1)
    assert "limit_except GET" in body and "deny all;" in body


# ── #1193-adjacent: realip trust structure in the reference config ─────


def test_realip_block_present_and_recursive(nginx_conf: str) -> None:
    """The reference config must carry the realip directives #1193 hardened
    host-side: a trusted-proxy set, X-Real-IP header, recursive resolution.
    (The trusted-IP *values* are deployment-specific and live-probe covered.)"""
    assert re.search(r"set_real_ip_from\s+\S+;", nginx_conf), "set_real_ip_from missing"
    assert re.search(r"real_ip_header\s+X-Real-IP;", nginx_conf), "real_ip_header missing"
    assert re.search(r"real_ip_recursive\s+on;", nginx_conf), "real_ip_recursive on missing"


def test_forwarded_headers_use_realip_peer(nginx_conf: str) -> None:
    """Upstream header injection must use the post-realip peer
    (``$remote_addr``), never the client-supplied forwarded values."""
    bodies = _location_blocks(nginx_conf)
    assert bodies, "no location blocks parsed"
    for body in bodies:
        if "proxy_set_header X-Real-IP" in body:
            assert "proxy_set_header X-Real-IP $remote_addr;" in body, "a location injects X-Real-IP from a non-realip source"
